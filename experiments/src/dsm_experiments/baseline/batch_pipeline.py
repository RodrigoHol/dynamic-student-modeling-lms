from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from dsm_common.config import (
    load_features_config,
    load_hle_catalog,
    load_windows_config,
)
from dsm_common.schemas import CanonicalEvent, FeatureVectorMessage, TraceMessage
from dsm_core.pipeline import PreprocessingEngine
from dsm_experiments.metrics import (
    compute_pm_fitness_and_precision,
    compute_silhouette,
    features_to_matrix,
)


@dataclass(slots=True)
class WindowBatchInput:
    granularity: str
    window_id: str
    features: list[FeatureVectorMessage]
    traces: list[TraceMessage]


@dataclass(slots=True)
class BatchWindowResult:
    granularity: str
    window_id: str
    student_labels: dict[str, int]
    silhouette_score: float | None
    pm_fitness: float | None
    pm_precision: float | None
    elapsed_ms: float


def materialize_windows_with_dsm_core(
    events: Sequence[CanonicalEvent],
    *,
    config_dir: Path,
) -> list[WindowBatchInput]:
    """Ejecuta exactamente el mismo ``PreprocessingEngine`` de dsm_core sobre eventos canónicos."""
    hle_cfg = load_hle_catalog(config_dir / "hle_catalog.yaml")
    feat_cfg = load_features_config(config_dir / "features.yaml")
    win_cfg = load_windows_config(config_dir / "windows.yaml")

    ordered = sorted(events, key=lambda ev: (ev.t, ev.event_id))
    if not ordered:
        return []

    course_start = ordered[0].t
    course_end = ordered[-1].t
    engine = PreprocessingEngine(
        hle_cfg,
        feat_cfg,
        win_cfg,
        course_start=course_start,
        course_end=course_end,
    )

    by_window_feat: dict[tuple[str, str], dict[str, FeatureVectorMessage]] = defaultdict(dict)
    by_window_trace: dict[tuple[str, str], dict[str, TraceMessage]] = defaultdict(dict)
    run_ids: set[str] = set()

    for ev in ordered:
        run_ids.add(ev.run_id)
        res = engine.process_event(ev)
        for fmsg, tmsg in res.outputs:
            wkey = (fmsg.granularity, fmsg.window_id)
            by_window_feat[wkey][fmsg.u] = fmsg
            by_window_trace[wkey][tmsg.u] = tmsg

    for rid in sorted(run_ids):
        for fmsg, tmsg in engine.flush_run(rid):
            wkey = (fmsg.granularity, fmsg.window_id)
            by_window_feat[wkey][fmsg.u] = fmsg
            by_window_trace[wkey][tmsg.u] = tmsg

    windows: list[WindowBatchInput] = []
    for wkey in sorted(by_window_feat):
        feats = sorted(by_window_feat[wkey].values(), key=lambda m: (m.window_start, m.u))
        traces = sorted(by_window_trace[wkey].values(), key=lambda m: (m.window_start, m.u))
        windows.append(
            WindowBatchInput(
                granularity=wkey[0],
                window_id=wkey[1],
                features=feats,
                traces=traces,
            )
        )
    return windows


def run_batch_kmeans_window(
    window: WindowBatchInput,
    *,
    n_clusters: int = 4,
    seed: int = 42,
) -> BatchWindowResult:
    started = perf_counter()
    feature_dicts = [f.features for f in window.features]
    students = [f.u for f in window.features]

    labels: list[int]
    if len(feature_dicts) < 2:
        labels = [0] * len(feature_dicts)
    else:
        matrix, _ = features_to_matrix(feature_dicts)
        scaled = StandardScaler().fit_transform(matrix) if matrix.shape[1] > 0 else matrix
        k = min(max(2, n_clusters), len(feature_dicts) - 1) if len(feature_dicts) >= 3 else 2
        model = KMeans(n_clusters=k, random_state=seed, n_init="auto")
        labels = [int(lbl) for lbl in model.fit_predict(scaled)]

    student_labels = dict(zip(students, labels, strict=True))
    silhouette = compute_silhouette(feature_dicts, labels, scale=True)
    fitness, precision = compute_pm_fitness_and_precision([t.trace for t in window.traces])
    elapsed_ms = round((perf_counter() - started) * 1000.0, 4)

    return BatchWindowResult(
        granularity=window.granularity,
        window_id=window.window_id,
        student_labels=student_labels,
        silhouette_score=silhouette,
        pm_fitness=fitness,
        pm_precision=precision,
        elapsed_ms=elapsed_ms,
    )
