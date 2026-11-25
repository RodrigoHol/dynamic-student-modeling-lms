from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from demo.runner import (
    REPLAYER_BIN,
    SYNTHETIC_DATASET,
    collect_topic_records,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings
from dsm_common.messaging import Topics


async def _verify_pg_and_kafka(settings: AppSettings, run_id: str) -> None:
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        run_row = await conn.fetchrow(
            "SELECT run_id, mode, status, speed_factor, events_processed "
            "FROM runs WHERE run_id = $1",
            run_id,
        )
        cfg_row = await conn.fetchrow(
            "SELECT run_id, clustering_algorithm, seed, features_version, hle_version "
            "FROM run_configs WHERE run_id = $1",
            run_id,
        )
    finally:
        await conn.close()

    if run_row is None or run_row["status"] != "completed" or run_row["events_processed"] != 5000:
        raise RuntimeError(f"Registro inválido en tabla runs para {run_id}: {run_row}")
    if cfg_row is None:
        raise RuntimeError(f"No se encontró snapshot en run_configs para {run_id}.")

    print(f"PostgreSQL runs -> {dict(run_row)}")
    print(f"PostgreSQL run_configs -> {dict(cfg_row)}")

    events = await collect_topic_records(
        settings.kafka_bootstrap_servers,
        Topics.CANONICAL_EVENTS,
        lambda ev: ev.get("run_id") == run_id and ev.get("event_type") != "run_eof",
    )
    per_student_ts: dict[str, list[datetime]] = defaultdict(list)
    for ev in events:
        per_student_ts[ev["u"]].append(datetime.fromisoformat(ev["t"]))

    out_of_order = sum(1 for ts_list in per_student_ts.values() if ts_list != sorted(ts_list))
    print(
        f"Kafka {Topics.CANONICAL_EVENTS} -> total={len(events)} | "
        f"estudiantes={len(per_student_ts)} | fuera_de_orden={out_of_order}"
    )
    if len(events) != 5000 or len(per_student_ts) != 50 or out_of_order != 0:
        raise RuntimeError(
            f"Verificación Kafka fallida (total={len(events)}, "
            f"estudiantes={len(per_student_ts)}, fuera_de_orden={out_of_order})."
        )


def verify_phase2(settings: AppSettings) -> None:
    print_header("ETAPA 3 — Comprobación de Fase 2 (Generador sintético + C3 Replayer)")
    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(SYNTHETIC_DATASET),
            "--target-events",
            "5000",
            "--students",
            "50",
            "--weeks",
            "8",
            "--seed",
            "42",
        ]
    )

    run_id = f"run_demo_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    run_cmd(
        [
            str(REPLAYER_BIN),
            "replay",
            str(SYNTHETIC_DATASET),
            "--speed",
            "max",
            "--run-id",
            run_id,
        ]
    )

    asyncio.run(_verify_pg_and_kafka(settings, run_id))
    print(f"\n[OK] Etapa 3 verificada: 5,000 eventos validados en PostgreSQL y Kafka ({run_id}).")
