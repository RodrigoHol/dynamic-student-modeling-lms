from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from demo.runner import (
    PHASE3_DATASET,
    PREPROCESSOR_URL,
    REPLAYER_BIN,
    collect_topic_records,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings
from dsm_common.messaging import Topics


def _normalize_features(
    records: list[dict[str, Any]],
    run_id: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rec in records:
        if rec["run_id"] != run_id:
            continue
        key = (rec["granularity"], rec["window_id"], rec["u"])
        result[key] = {
            "course_id": rec["course_id"],
            "window_start": rec["window_start"],
            "window_end": rec["window_end"],
            "features_version": rec["features_version"],
            "hle_version": rec["hle_version"],
            "event_count": rec["event_count"],
            "features": rec["features"],
        }
    return result


def _normalize_traces(
    records: list[dict[str, Any]],
    run_id: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rec in records:
        if rec["run_id"] != run_id:
            continue
        key = (rec["granularity"], rec["window_id"], rec["u"])
        result[key] = {
            "course_id": rec["course_id"],
            "window_start": rec["window_start"],
            "window_end": rec["window_end"],
            "hle_version": rec["hle_version"],
            "event_count": rec["event_count"],
            "trace": [
                (
                    item["hle"],
                    item["t"],
                    item["a"],
                    item["resource_id"],
                    item["resource_type"],
                    item.get("session_hash"),
                )
                for item in rec["trace"]
            ],
        }
    return result


async def _check_c4_health() -> None:
    async with httpx.AsyncClient(base_url=PREPROCESSOR_URL, timeout=10.0) as client:
        resp = await client.get("/health")
        if resp.status_code != 200 or resp.json().get("status") != "ok":
            raise RuntimeError(f"Healthcheck inválido en C4 Preprocessor: {resp.text}")
        print(f"C4 /health -> {resp.status_code} {resp.json()}")


async def _verify_determinism(
    settings: AppSettings,
    run_10x: str,
    run_max: str,
    *,
    expected_students: int = 10,
    timeout_seconds: float = 45.0,
) -> None:
    target_runs = {run_10x, run_max}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    feat_records: list[dict[str, Any]] = []
    trace_records: list[dict[str, Any]] = []
    while loop.time() < deadline:
        feat_records = await collect_topic_records(
            settings.kafka_bootstrap_servers,
            Topics.FEATURES,
            lambda r: r.get("run_id") in target_runs,
        )
        trace_records = await collect_topic_records(
            settings.kafka_bootstrap_servers,
            Topics.TRACES,
            lambda r: r.get("run_id") in target_runs,
        )
        counts = [
            len({r["u"] for r in recs if r["run_id"] == rid and r["granularity"] == "course"})
            for recs in (feat_records, trace_records)
            for rid in (run_10x, run_max)
        ]
        if all(count >= expected_students for count in counts):
            break
        await asyncio.sleep(1.0)

    feats_10x = _normalize_features(feat_records, run_10x)
    feats_max = _normalize_features(feat_records, run_max)
    traces_10x = _normalize_traces(trace_records, run_10x)
    traces_max = _normalize_traces(trace_records, run_max)

    if not feats_10x or not traces_10x:
        raise RuntimeError(
            "No se recibieron ventanas en analytics.features / analytics.traces dentro del timeout."
        )

    granularities_feat = {k[0] for k in feats_10x}
    granularities_trace = {k[0] for k in traces_10x}
    expected_grans = {"daily", "weekly", "monthly", "course"}
    if granularities_feat != expected_grans or granularities_trace != expected_grans:
        raise RuntimeError(
            f"Faltan granularidades en salida (features={sorted(granularities_feat)}, "
            f"traces={sorted(granularities_trace)})."
        )

    leaked_noise = [
        item for rec in traces_10x.values() for item in rec["trace"] if item[4] == "report"
    ]
    if leaked_noise:
        raise RuntimeError(f"Se filtraron eventos de ruido en analytics.traces: {leaked_noise[:3]}")

    if feats_10x != feats_max:
        diff_keys = sorted(set(feats_10x) ^ set(feats_max))
        raise RuntimeError(
            f"Divergencia de determinismo 10x vs max en analytics.features (claves={diff_keys[:5]})"
        )
    if traces_10x != traces_max:
        diff_keys = sorted(set(traces_10x) ^ set(traces_max))
        raise RuntimeError(
            f"Divergencia de determinismo 10x vs max en analytics.traces (claves={diff_keys[:5]})"
        )

    print(
        f"analytics.features OK -> {len(feats_10x)} ventanas idénticas (10x == max) | "
        f"granularidades={sorted(granularities_feat)}"
    )
    print(
        f"analytics.traces   OK -> {len(traces_10x)} trazas idénticas (10x == max) | "
        "ruido filtrado=100%"
    )


def verify_phase3(settings: AppSettings) -> None:
    print_header("ETAPA 4 — Comprobación de Fase 3 (C4 Preprocessor + Determinismo 10x vs max)")
    asyncio.run(_check_c4_health())

    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(PHASE3_DATASET),
            "--target-events",
            "240",
            "--students",
            "10",
            "--weeks",
            "8",
            "--seed",
            "77",
            "--noise-ratio",
            "0.05",
        ]
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:4]
    run_10x = f"run_p3_10x_{stamp}_{suffix}"
    run_max = f"run_p3_max_{stamp}_{suffix}"

    run_cmd(
        [
            str(REPLAYER_BIN),
            "replay",
            str(PHASE3_DATASET),
            "--speed",
            "10x",
            "--max-delay",
            "0.015",
            "--run-id",
            run_10x,
        ]
    )
    run_cmd(
        [
            str(REPLAYER_BIN),
            "replay",
            str(PHASE3_DATASET),
            "--speed",
            "max",
            "--run-id",
            run_max,
        ]
    )

    asyncio.run(_verify_determinism(settings, run_10x, run_max))
    print(
        f"\n[OK] Etapa 4 verificada: determinismo 100% entre {run_10x} (10x) y {run_max} (max)."
    )
