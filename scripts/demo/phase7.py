from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from pymongo import AsyncMongoClient

from demo.runner import (
    EXPERIMENTS_BIN,
    GRAFANA_URL,
    PHASE7_DATASET,
    PROMETHEUS_URL,
    REPLAYER_BIN,
    REPO_ROOT,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings
from dsm_common.storage import PostgresRunRepository


async def _wait_for_observability(timeout_seconds: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    async with httpx.AsyncClient(timeout=5.0) as client:
        while loop.time() < deadline:
            try:
                p = await client.get(f"{PROMETHEUS_URL}/-/ready")
                g = await client.get(f"{GRAFANA_URL}/api/health")
                if p.status_code == 200 and g.status_code == 200:
                    print(f"Prometheus -> {p.status_code} | Grafana -> {g.status_code}")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    raise RuntimeError("Prometheus o Grafana no respondieron dentro del timeout.")


async def _wait_for_mongo_profiles(
    settings: AppSettings,
    run_id: str,
    *,
    expected_students: int = 30,
    timeout_seconds: float = 60.0,
) -> None:
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    db = client[settings.mongo_db]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        while loop.time() < deadline:
            profiles = await db["student_profiles"].find({"run_id": run_id}).to_list(length=None)
            course_students = {
                doc["student_id"] for doc in profiles if doc.get("granularity") == "course"
            }
            if len(course_students) >= expected_students:
                return
            await asyncio.sleep(1.0)
    finally:
        await client.close()
    raise RuntimeError(f"MongoDB no completó los perfiles para '{run_id}'.")


async def _verify_pg_metrics(settings: AppSettings, run_id: str) -> int:
    repo = PostgresRunRepository(settings.postgres_dsn)
    try:
        rows = await repo.list_experiment_metrics(run_id)
        return len(rows)
    finally:
        await repo.close()


def verify_phase7(settings: AppSettings) -> None:
    print_header(
        "ETAPA 8 — Comprobación de Fase 7 (C9 Experiment Runner + C10 Prometheus/Grafana)"
    )
    asyncio.run(_wait_for_observability())

    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(PHASE7_DATASET),
            "--target-events",
            "1500",
            "--students",
            "30",
            "--weeks",
            "8",
            "--seed",
            "88",
            "--noise-ratio",
            "0.05",
        ]
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_p7_{stamp}_{uuid4().hex[:4]}"
    run_cmd(
        [str(REPLAYER_BIN), "replay", str(PHASE7_DATASET), "--speed", "max", "--run-id", run_id]
    )
    asyncio.run(_wait_for_mongo_profiles(settings, run_id))

    live_out = REPO_ROOT / "experiments" / "results" / f"live_{run_id}"
    bench_out = REPO_ROOT / "experiments" / "results" / f"bench_{run_id}"

    run_cmd(
        [
            str(EXPERIMENTS_BIN),
            "evaluate-run",
            run_id,
            "--dataset",
            str(PHASE7_DATASET),
            "--output-dir",
            str(live_out),
        ]
    )
    run_cmd(
        [
            str(EXPERIMENTS_BIN),
            "benchmark",
            str(PHASE7_DATASET),
            "--experiment-id",
            f"bench_{run_id}",
            "--output-dir",
            str(bench_out),
        ]
    )

    count = asyncio.run(_verify_pg_metrics(settings, run_id))
    if count <= 0:
        raise RuntimeError(f"No se insertaron filas en experiment_metrics para '{run_id}'.")

    expected_files = (
        "metrics_summary.csv",
        "comparison_table.tex",
        "summary.json",
        "comparison_metrics.png",
    )
    for fname in expected_files:
        if not (bench_out / fname).is_file():
            raise RuntimeError(f"Falta archivo exportado por C9: {bench_out / fname}")

    print(
        f"\n[OK] Etapa 8 verificada: {count} métricas en PostgreSQL ({run_id}), "
        f"reportes en {bench_out}, Prometheus y Grafana operativos."
    )
