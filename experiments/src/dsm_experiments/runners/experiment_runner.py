from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from dsm_common.config import AppSettings, load_clustering_config
from dsm_common.privacy import pseudonymize_user_id
from dsm_common.schemas import CanonicalEvent, EventMetadata, RawEventInput, ResourceInfo
from dsm_common.storage import (
    ExperimentMetricRecord,
    RunRepository,
    load_run_config_snapshot,
)
from dsm_common.time import ensure_utc, utc_now
from dsm_core.clustering import ClusteringEngine
from dsm_experiments.baseline import (
    BatchWindowResult,
    WindowBatchInput,
    materialize_windows_with_dsm_core,
    run_batch_kmeans_window,
)
from dsm_experiments.metrics import (
    compute_ari,
    compute_pm_fitness_and_precision,
    compute_silhouette,
    compute_throughput_eps,
    summarize_latencies_ms,
)
from dsm_experiments.reports import export_benchmark_reports


class BenchmarkRow(BaseModel):
    method: str
    granularity: str
    window_id: str
    student_count: int
    cluster_count: int
    silhouette_score: float | None = None
    ari_vs_batch: float | None = None
    ari_reproducibility: float | None = None
    pm_fitness: float | None = None
    pm_precision: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    throughput_eps: float | None = None


class MethodSummary(BaseModel):
    method: str
    granularity: str
    windows_evaluated: int
    mean_silhouette: float | None = None
    mean_ari_vs_batch: float | None = None
    mean_ari_reproducibility: float | None = None
    mean_pm_fitness: float | None = None
    mean_pm_precision: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    throughput_eps: float | None = None


class BenchmarkReport(BaseModel):
    experiment_id: str
    dataset_path: str
    events_count: int
    windows_count: int
    generated_at: datetime
    rows: list[BenchmarkRow] = Field(default_factory=list)
    method_summaries: list[MethodSummary] = Field(default_factory=list)


def load_canonical_events_from_jsonl(
    dataset_path: Path,
    *,
    salt: str = "benchmark-salt",
    run_id: str = "exp_benchmark",
) -> list[CanonicalEvent]:
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset no encontrado: {dataset_path}")

    events: list[CanonicalEvent] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            stripped = line.strip()
            if not stripped:
                continue
            raw: dict[str, Any] = json.loads(stripped)
            if {"event_id", "u", "a", "r", "t", "M"}.issubset(raw.keys()):
                events.append(CanonicalEvent.model_validate(raw))
                continue

            parsed = RawEventInput.model_validate(raw)
            pseudo_u = pseudonymize_user_id(parsed.raw_user_id, salt)
            events.append(
                CanonicalEvent(
                    event_id=f"exp_{idx:08d}",
                    run_id=run_id,
                    u=pseudo_u,
                    a=parsed.action,
                    r=ResourceInfo(
                        resource_id=parsed.resource.resource_id,
                        resource_type=parsed.resource.resource_type,
                        name=parsed.resource.name,
                    ),
                    t=ensure_utc(parsed.timestamp),
                    ingested_at=utc_now(),
                    M=EventMetadata(
                        course_id=parsed.metadata.course_id,
                        source_format=parsed.metadata.source_format,
                        component=parsed.metadata.component,
                        raw_eventname=parsed.metadata.raw_eventname,
                        hle=parsed.metadata.hle,
                        session_hash=parsed.metadata.session_hash,
                    ),
                )
            )
    return events


def _mean_or_none(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(float(mean(present)), 6) if present else None


def _run_stream_clustering(
    windows: Sequence[WindowBatchInput],
    *,
    config_dir: Path,
    algorithm: str,
) -> tuple[dict[tuple[str, str], dict[str, int]], dict[tuple[str, str], list[float]], float]:
    base_cfg = load_clustering_config(config_dir / "clustering.yaml")
    algo_cfg = base_cfg.model_copy(update={"algorithm": algorithm})
    engine = ClusteringEngine(algo_cfg)

    labels_by_window: dict[tuple[str, str], dict[str, int]] = {}
    latencies_by_window: dict[tuple[str, str], list[float]] = defaultdict(list)

    ordered_windows = sorted(
        windows,
        key=lambda w: (
            w.granularity,
            w.features[0].window_start if w.features else utc_now(),
            w.window_id,
        ),
    )

    total_vectors = 0
    t_start = perf_counter()
    for win in ordered_windows:
        wkey = (win.granularity, win.window_id)
        w_labels: dict[str, int] = {}
        for fmsg in win.features:
            vec_start = perf_counter()
            step = engine.process_vector(fmsg)
            latencies_by_window[wkey].append((perf_counter() - vec_start) * 1000.0)
            w_labels[fmsg.u] = step.assignment.cluster_id
            total_vectors += 1
        labels_by_window[wkey] = w_labels
    total_elapsed_sec = max(1e-6, perf_counter() - t_start)
    throughput = compute_throughput_eps(total_vectors, total_elapsed_sec)
    return labels_by_window, latencies_by_window, throughput


def _build_method_summaries(rows: Sequence[BenchmarkRow]) -> list[MethodSummary]:
    grouped: dict[tuple[str, str], list[BenchmarkRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.method, row.granularity)].append(row)
        grouped[(row.method, "all")].append(row)

    summaries: list[MethodSummary] = []
    for (method, granularity), items in sorted(grouped.items()):
        summaries.append(
            MethodSummary(
                method=method,
                granularity=granularity,
                windows_evaluated=len(items),
                mean_silhouette=_mean_or_none([r.silhouette_score for r in items]),
                mean_ari_vs_batch=_mean_or_none([r.ari_vs_batch for r in items]),
                mean_ari_reproducibility=_mean_or_none([r.ari_reproducibility for r in items]),
                mean_pm_fitness=_mean_or_none([r.pm_fitness for r in items]),
                mean_pm_precision=_mean_or_none([r.pm_precision for r in items]),
                p50_latency_ms=_mean_or_none([r.p50_latency_ms for r in items]),
                p95_latency_ms=_mean_or_none([r.p95_latency_ms for r in items]),
                p99_latency_ms=_mean_or_none([r.p99_latency_ms for r in items]),
                throughput_eps=_mean_or_none([r.throughput_eps for r in items]),
            )
        )
    return summaries


async def run_in_memory_benchmark(
    events: Sequence[CanonicalEvent],
    *,
    config_dir: Path,
    dataset_label: str = "in_memory",
    experiment_id: str | None = None,
    n_clusters_batch: int = 4,
    run_repository: RunRepository | None = None,
    output_dir: Path | None = None,
) -> BenchmarkReport:
    exp_id = experiment_id or f"exp_{utc_now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    windows = materialize_windows_with_dsm_core(events, config_dir=config_dir)

    batch_results: dict[tuple[str, str], BatchWindowResult] = {}
    batch_total_start = perf_counter()
    for win in windows:
        batch_results[(win.granularity, win.window_id)] = run_batch_kmeans_window(
            win,
            n_clusters=n_clusters_batch,
        )
    batch_elapsed = max(1e-6, perf_counter() - batch_total_start)
    batch_throughput = compute_throughput_eps(len(events), batch_elapsed)

    # Ejecutar DenStream (x2 para ARI de reproducibilidad) y DBSTREAM sobre los mismos vectores
    den_1, den_lat, den_tp = _run_stream_clustering(
        windows, config_dir=config_dir, algorithm="denstream"
    )
    den_2, _, _ = _run_stream_clustering(
        windows, config_dir=config_dir, algorithm="denstream"
    )
    db_1, db_lat, db_tp = _run_stream_clustering(
        windows, config_dir=config_dir, algorithm="dbstream"
    )
    db_2, _, _ = _run_stream_clustering(
        windows, config_dir=config_dir, algorithm="dbstream"
    )

    rows: list[BenchmarkRow] = []
    pm_cache: dict[tuple[str, str], tuple[float | None, float | None]] = {}

    for win in windows:
        wkey = (win.granularity, win.window_id)
        batch_res = batch_results[wkey]
        pm_cache[wkey] = (batch_res.pm_fitness, batch_res.pm_precision)
        students = [f.u for f in win.features]
        feature_dicts = [f.features for f in win.features]
        batch_labels = [batch_res.student_labels[u] for u in students]

        rows.append(
            BenchmarkRow(
                method="batch_kmeans",
                granularity=win.granularity,
                window_id=win.window_id,
                student_count=len(students),
                cluster_count=len(set(batch_labels)),
                silhouette_score=batch_res.silhouette_score,
                ari_vs_batch=1.0 if len(students) >= 2 else None,
                ari_reproducibility=1.0 if len(students) >= 2 else None,
                pm_fitness=batch_res.pm_fitness,
                pm_precision=batch_res.pm_precision,
                p50_latency_ms=batch_res.elapsed_ms,
                p95_latency_ms=batch_res.elapsed_ms,
                p99_latency_ms=batch_res.elapsed_ms,
                throughput_eps=batch_throughput,
            )
        )

        for method_name, primary, repeat, latencies, tp in (
            ("stream_denstream", den_1, den_2, den_lat, den_tp),
            ("stream_dbstream", db_1, db_2, db_lat, db_tp),
        ):
            s_labels_map = primary[wkey]
            r_labels_map = repeat[wkey]
            s_labels = [s_labels_map[u] for u in students]
            r_labels = [r_labels_map[u] for u in students]
            lat_summary = summarize_latencies_ms(latencies[wkey])

            rows.append(
                BenchmarkRow(
                    method=method_name,
                    granularity=win.granularity,
                    window_id=win.window_id,
                    student_count=len(students),
                    cluster_count=len({lbl for lbl in s_labels if lbl >= 0}),
                    silhouette_score=compute_silhouette(feature_dicts, s_labels, scale=True),
                    ari_vs_batch=compute_ari(s_labels, batch_labels),
                    ari_reproducibility=compute_ari(s_labels, r_labels),
                    pm_fitness=pm_cache[wkey][0],
                    pm_precision=pm_cache[wkey][1],
                    p50_latency_ms=lat_summary.p50_ms,
                    p95_latency_ms=lat_summary.p95_ms,
                    p99_latency_ms=lat_summary.p99_ms,
                    throughput_eps=tp,
                )
            )

    summaries = _build_method_summaries(rows)
    report = BenchmarkReport(
        experiment_id=exp_id,
        dataset_path=dataset_label,
        events_count=len(events),
        windows_count=len(windows),
        generated_at=utc_now(),
        rows=rows,
        method_summaries=summaries,
    )

    if run_repository is not None:
        snapshot = load_run_config_snapshot(config_dir)
        for method_name, mode in (
            ("batch_kmeans", "batch"),
            ("stream_denstream", "stream"),
            ("stream_dbstream", "stream"),
        ):
            run_id = f"{exp_id}_{method_name}"
            await run_repository.start_run(
                run_id=run_id,
                mode=mode,  # type: ignore[arg-type]
                source_dataset=dataset_label,
                speed_factor="max",
                config_snapshot=snapshot,
            )
            await run_repository.complete_run(run_id, events_processed=len(events))
            records = [
                ExperimentMetricRecord(
                    run_id=run_id,
                    granularity=r.granularity,
                    window_id=r.window_id,
                    silhouette_score=r.silhouette_score,
                    ari_score=r.ari_vs_batch,
                    pm_fitness=r.pm_fitness,
                    pm_precision=r.pm_precision,
                    p50_latency_ms=r.p50_latency_ms,
                    p95_latency_ms=r.p95_latency_ms,
                    p99_latency_ms=r.p99_latency_ms,
                    throughput_eps=r.throughput_eps,
                )
                for r in rows
                if r.method == method_name
            ]
            await run_repository.insert_experiment_metrics(records)

    if output_dir is not None:
        export_benchmark_reports(report, output_dir)

    return report


async def evaluate_live_run(
    *,
    run_id: str,
    dataset_path: Path,
    settings: AppSettings,
    n_clusters_batch: int = 4,
    output_dir: Path | None = None,
) -> list[ExperimentMetricRecord]:
    from pymongo import AsyncMongoClient

    from dsm_common.storage import PostgresRunRepository

    events = load_canonical_events_from_jsonl(
        dataset_path,
        salt=settings.pseudonym_salt,
        run_id=run_id,
    )
    windows = materialize_windows_with_dsm_core(events, config_dir=settings.config_dir)
    if not windows:
        raise RuntimeError(f"No se generaron ventanas desde {dataset_path}.")

    mongo = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    try:
        db = mongo[settings.mongo_db]
        profiles = await db["student_profiles"].find({"run_id": run_id}).to_list(length=None)
    finally:
        await mongo.close()

    if not profiles:
        raise RuntimeError(f"No se encontraron perfiles en MongoDB para run_id='{run_id}'.")

    stream_labels: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    stream_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
    for prof in profiles:
        wkey = (str(prof["granularity"]), str(prof["window_id"]))
        stream_labels[wkey][str(prof["student_id"])] = int(prof["clustering"]["cluster_id"])
        lat = prof.get("latencies_ms", {}).get("ingested_to_profile")
        if lat is not None:
            stream_latencies[wkey].append(float(lat))

    pg_repo = PostgresRunRepository(settings.postgres_dsn)
    try:
        run_rec = await pg_repo.get_run(run_id)
        throughput = None
        if run_rec and run_rec.finished_at and run_rec.started_at:
            elapsed = (run_rec.finished_at - run_rec.started_at).total_seconds()
            throughput = compute_throughput_eps(run_rec.events_processed or len(events), elapsed)

        records: list[ExperimentMetricRecord] = []
        rows: list[BenchmarkRow] = []

        for win in windows:
            wkey = (win.granularity, win.window_id)
            s_map = stream_labels.get(wkey)
            if not s_map:
                continue
            batch_res = run_batch_kmeans_window(win, n_clusters=n_clusters_batch)
            common_students = [f.u for f in win.features if f.u in s_map]
            if not common_students:
                continue
            feature_dicts = [f.features for f in win.features if f.u in s_map]
            s_lbls = [s_map[u] for u in common_students]
            b_lbls = [batch_res.student_labels[u] for u in common_students]

            sil = compute_silhouette(feature_dicts, s_lbls, scale=True)
            ari = compute_ari(s_lbls, b_lbls)
            fitness, precision = compute_pm_fitness_and_precision([t.trace for t in win.traces])
            lat_sum = summarize_latencies_ms(stream_latencies[wkey])

            records.append(
                ExperimentMetricRecord(
                    run_id=run_id,
                    granularity=win.granularity,
                    window_id=win.window_id,
                    silhouette_score=sil,
                    ari_score=ari,
                    pm_fitness=fitness,
                    pm_precision=precision,
                    p50_latency_ms=lat_sum.p50_ms,
                    p95_latency_ms=lat_sum.p95_ms,
                    p99_latency_ms=lat_sum.p99_ms,
                    throughput_eps=throughput,
                )
            )
            rows.append(
                BenchmarkRow(
                    method="live_stream",
                    granularity=win.granularity,
                    window_id=win.window_id,
                    student_count=len(common_students),
                    cluster_count=len({lbl for lbl in s_lbls if lbl >= 0}),
                    silhouette_score=sil,
                    ari_vs_batch=ari,
                    pm_fitness=fitness,
                    pm_precision=precision,
                    p50_latency_ms=lat_sum.p50_ms,
                    p95_latency_ms=lat_sum.p95_ms,
                    p99_latency_ms=lat_sum.p99_ms,
                    throughput_eps=throughput,
                )
            )

        await pg_repo.insert_experiment_metrics(records)
        if output_dir is not None and rows:
            report = BenchmarkReport(
                experiment_id=run_id,
                dataset_path=str(dataset_path),
                events_count=len(events),
                windows_count=len(rows),
                generated_at=utc_now(),
                rows=rows,
                method_summaries=_build_method_summaries(rows),
            )
            export_benchmark_reports(report, output_dir)
        return records
    finally:
        await pg_repo.close()
