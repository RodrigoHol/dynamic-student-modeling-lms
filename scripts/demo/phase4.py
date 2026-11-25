from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from statistics import median
from typing import Any
from uuid import uuid4

import httpx
from pymongo import AsyncMongoClient

from demo.runner import (
    CLUSTERING_URL,
    PHASE4_DATASET,
    REPLAYER_BIN,
    REPO_ROOT,
    collect_topic_records,
    compose_cmd,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings
from dsm_common.messaging import Topics

EXPECTED_GRANULARITIES = {"daily", "weekly", "monthly", "course"}


async def _wait_for_c5_health(timeout_seconds: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    async with httpx.AsyncClient(base_url=CLUSTERING_URL, timeout=5.0) as client:
        while loop.time() < deadline:
            try:
                resp = await client.get("/health")
                if resp.status_code == 200 and resp.json().get("status") == "ok":
                    print(f"C5 /health -> {resp.status_code} {resp.json()}")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    raise RuntimeError("C5 Clustering Engine no respondió /health == 200 dentro del timeout.")


async def _wait_and_verify_mongo_run(
    settings: AppSettings,
    run_id: str,
    *,
    expected_algorithm: str,
    expected_students: int = 30,
    timeout_seconds: float = 60.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    db = client[settings.mongo_db]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    profiles: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    try:
        while loop.time() < deadline:
            profiles = await db["student_profiles"].find({"run_id": run_id}).to_list(length=None)
            snapshots = await db["cluster_snapshots"].find({"run_id": run_id}).to_list(length=None)
            course_students = {
                doc["student_id"] for doc in profiles if doc.get("granularity") == "course"
            }
            prof_grans = {doc.get("granularity") for doc in profiles}
            snap_grans = {doc.get("granularity") for doc in snapshots}
            if (
                len(course_students) >= expected_students
                and prof_grans == EXPECTED_GRANULARITIES
                and snap_grans == EXPECTED_GRANULARITIES
            ):
                break
            await asyncio.sleep(1.0)
    finally:
        await client.close()

    if not profiles or not snapshots:
        raise RuntimeError(
            f"No se persistieron perfiles/snapshots para '{run_id}' en MongoDB."
        )

    prof_grans = {doc.get("granularity") for doc in profiles}
    snap_grans = {doc.get("granularity") for doc in snapshots}
    if prof_grans != EXPECTED_GRANULARITIES or snap_grans != EXPECTED_GRANULARITIES:
        raise RuntimeError(
            f"Granularidades incompletas en MongoDB para '{run_id}' "
            f"(profiles={sorted(prof_grans)}, snapshots={sorted(snap_grans)})."
        )

    for doc in profiles:
        clustering_meta = doc.get("clustering", {})
        if clustering_meta.get("algorithm") != expected_algorithm:
            raise RuntimeError(
                f"Algoritmo inesperado en perfil {doc.get('_id')}: "
                f"{clustering_meta.get('algorithm')} != {expected_algorithm}"
            )
        for required_key in ("cluster_id", "previous_cluster_id", "transition_detected"):
            if required_key not in clustering_meta:
                raise RuntimeError(f"Falta '{required_key}' en clustering de {doc.get('_id')}.")
        top_feats = doc.get("explainability", {}).get("top_contributing_features", [])
        if not top_feats:
            raise RuntimeError(
                f"top_contributing_features vacío en {doc.get('_id')}."
            )
        latency = doc.get("latencies_ms", {}).get("ingested_to_profile", -1)
        if latency < 0:
            raise RuntimeError(f"Latencia inválida en {doc.get('_id')}: {latency}")

    for snap in snapshots:
        if snap.get("algorithm") != expected_algorithm:
            raise RuntimeError(
                f"Algoritmo inesperado en snapshot {snap.get('_id')}: {snap.get('algorithm')}"
            )

    return profiles, snapshots


async def _verify_assignments_topic(
    settings: AppSettings,
    run_id: str,
    *,
    expected_algorithm: str,
    expected_count: int,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    records: list[dict[str, Any]] = []
    while loop.time() < deadline:
        records = await collect_topic_records(
            settings.kafka_bootstrap_servers,
            Topics.ASSIGNMENTS,
            lambda r: r.get("run_id") == run_id,
        )
        if len(records) >= expected_count:
            break
        await asyncio.sleep(1.0)

    if len(records) < expected_count:
        raise RuntimeError(
            f"Se esperaban >= {expected_count} mensajes en {Topics.ASSIGNMENTS} "
            f"para '{run_id}', se encontraron {len(records)}."
        )
    if any(rec.get("algorithm") != expected_algorithm for rec in records):
        raise RuntimeError(f"Algoritmo inconsistente en {Topics.ASSIGNMENTS} para '{run_id}'.")
    return records


def _summarize_run(
    label: str,
    profiles: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    assignments_count: int,
) -> None:
    weekly_clusters = sorted(
        {
            doc["clustering"]["cluster_id"]
            for doc in profiles
            if doc.get("granularity") == "weekly"
            and not doc["clustering"].get("is_outlier", False)
        }
    )
    transitions = sum(
        1 for doc in profiles if doc.get("clustering", {}).get("transition_detected")
    )
    latencies = [doc["latencies_ms"]["ingested_to_profile"] for doc in profiles]
    print(
        f"[{label}] MongoDB OK -> {len(profiles)} perfiles | {len(snapshots)} snapshots | "
        f"clústeres weekly={weekly_clusters} | transiciones={transitions} | "
        f"latencia p50={median(latencies):.0f} ms | Kafka assignments={assignments_count}"
    )


def _switch_clustering_algorithm(target_algo: str) -> str:
    cfg_path = REPO_ROOT / "config" / "clustering.yaml"
    original = cfg_path.read_text(encoding="utf-8")
    updated_lines = [
        f"algorithm: {target_algo}" if line.startswith("algorithm:") else line
        for line in original.splitlines()
    ]
    cfg_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return original


def verify_phase4(settings: AppSettings) -> None:
    print_header(
        "ETAPA 5 — Comprobación de Fase 4 (C5 Clustering + MongoDB + DenStream -> DBSTREAM)"
    )
    asyncio.run(_wait_for_c5_health())

    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(PHASE4_DATASET),
            "--target-events",
            "1500",
            "--students",
            "30",
            "--weeks",
            "8",
            "--seed",
            "99",
            "--noise-ratio",
            "0.05",
        ]
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:4]
    run_den = f"run_p4_den_{stamp}_{suffix}"
    run_db = f"run_p4_db_{stamp}_{suffix}"

    run_cmd(
        [str(REPLAYER_BIN), "replay", str(PHASE4_DATASET), "--speed", "max", "--run-id", run_den]
    )

    den_profiles, den_snaps = asyncio.run(
        _wait_and_verify_mongo_run(settings, run_den, expected_algorithm="denstream")
    )
    den_assigns = asyncio.run(
        _verify_assignments_topic(
            settings,
            run_den,
            expected_algorithm="denstream",
            expected_count=len(den_profiles),
        )
    )
    _summarize_run("DenStream", den_profiles, den_snaps, len(den_assigns))

    cfg_path = REPO_ROOT / "config" / "clustering.yaml"
    original_yaml = _switch_clustering_algorithm("dbstream")
    try:
        print("\nCambiando config/clustering.yaml a algorithm: dbstream y reiniciando C5...")
        run_cmd(compose_cmd("restart", "clustering"))
        asyncio.run(_wait_for_c5_health())

        run_cmd(
            [str(REPLAYER_BIN), "replay", str(PHASE4_DATASET), "--speed", "max", "--run-id", run_db]
        )
        db_profiles, db_snaps = asyncio.run(
            _wait_and_verify_mongo_run(settings, run_db, expected_algorithm="dbstream")
        )
        db_assigns = asyncio.run(
            _verify_assignments_topic(
                settings,
                run_db,
                expected_algorithm="dbstream",
                expected_count=len(db_profiles),
            )
        )
        _summarize_run("DBSTREAM", db_profiles, db_snaps, len(db_assigns))
    finally:
        cfg_path.write_text(original_yaml, encoding="utf-8")
        print("\nRestaurando config/clustering.yaml a denstream y reiniciando C5...")
        run_cmd(compose_cmd("restart", "clustering"))
        asyncio.run(_wait_for_c5_health())

    print(
        f"\n[OK] Etapa 5 verificada: DenStream ({run_den}) y DBSTREAM ({run_db}) "
        "persistidos en MongoDB y analytics.assignments."
    )
