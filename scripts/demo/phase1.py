from __future__ import annotations

import asyncio

import asyncpg
import httpx

from demo.runner import compose_cmd, print_header, run_capture, run_cmd
from dsm_common.config import AppSettings

EXPECTED_PG_TABLES = {
    "courses",
    "experiment_metrics",
    "hle_catalog_versions",
    "resources",
    "run_configs",
    "runs",
    "users_roles",
}


async def _verify_gateway_and_pg(settings: AppSettings) -> None:
    gateway_url = settings.gateway_url.rstrip("/")
    async with httpx.AsyncClient(base_url=gateway_url, timeout=15.0) as client:
        health_resp = await client.get("/health")
        if health_resp.status_code != 200 or health_resp.json().get("status") != "ok":
            raise RuntimeError(f"Healthcheck inválido en C2: {health_resp.text}")
        print(f"C2 /health -> {health_resp.status_code} {health_resp.json()}")

        valid_payload = {
            "raw_user_id": "alu_demo_01",
            "action": "submitted",
            "resource": {
                "resource_id": "assign_03",
                "resource_type": "assign",
                "name": "Tarea 3",
            },
            "timestamp": "2024-09-18T14:23:11Z",
            "metadata": {
                "course_id": "course_105",
                "source_format": "moodle_csv",
                "component": "mod_assign",
            },
        }
        ok_resp = await client.post("/api/v1/events", json=valid_payload)
        ok_body = ok_resp.json()
        if ok_resp.status_code != 202 or ok_body.get("status") != "accepted":
            raise RuntimeError(f"Error al ingerir evento válido: {ok_resp.status_code} {ok_body}")
        pseudo_u = str(ok_body.get("u", ""))
        if not pseudo_u.startswith("usr_") or pseudo_u == "alu_demo_01":
            raise RuntimeError(f"Seudonimización inválida en respuesta: {ok_body}")
        print(
            f"C2 evento válido -> HTTP 202 | u={pseudo_u} | "
            f"ingested_at={ok_body.get('ingested_at')}"
        )

        bad_payload = {"raw_user_id": "alu_demo_01", "action": ""}
        dlq_resp = await client.post("/api/v1/events", json=bad_payload)
        dlq_body = dlq_resp.json()
        if dlq_resp.status_code != 422 or dlq_body.get("status") != "dlq":
            raise RuntimeError(
                f"Se esperaba HTTP 422 hacia DLQ: {dlq_resp.status_code} {dlq_body}"
            )
        print(f"C2 evento inválido -> HTTP 422 (DLQ) | dlq_id={dlq_body.get('dlq_id')}")

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        found_tables = {row["tablename"] for row in rows}
    finally:
        await conn.close()

    missing = EXPECTED_PG_TABLES - found_tables
    if missing:
        raise RuntimeError(f"Faltan tablas en PostgreSQL: {sorted(missing)}")
    print(f"PostgreSQL OK -> {len(EXPECTED_PG_TABLES)} tablas verificadas: {sorted(found_tables)}")


def verify_phase1(settings: AppSettings) -> None:
    print_header("ETAPA 2 — Comprobación de Fase 1 (Infraestructura Kappa + C2 Gateway)")
    run_cmd(compose_cmd("up", "-d", "--wait"))
    run_cmd(compose_cmd("ps"))

    run_cmd(
        [
            "docker",
            "exec",
            "dsm-neo4j",
            "cypher-shell",
            "-u",
            settings.neo4j_user,
            "-p",
            settings.neo4j_password,
            "-f",
            "/init/constraints.cypher",
        ]
    )

    asyncio.run(_verify_gateway_and_pg(settings))

    mongo_out = run_capture(
        [
            "docker",
            "exec",
            "dsm-mongodb",
            "mongosh",
            settings.mongo_db,
            "--quiet",
            "--eval",
            "JSON.stringify(db.student_profiles.getIndexes().map(i => i.name))",
        ]
    )
    if "uq_profile_run_gran_window_student" not in mongo_out:
        raise RuntimeError(f"No se encontró el índice esperado en MongoDB: {mongo_out}")
    print("MongoDB OK -> índice único compuesto verificado en student_profiles.")

    neo4j_out = run_capture(
        [
            "docker",
            "exec",
            "dsm-neo4j",
            "cypher-shell",
            "-u",
            settings.neo4j_user,
            "-p",
            settings.neo4j_password,
            "SHOW CONSTRAINTS;",
        ]
    )
    if "Activity" not in neo4j_out or "Boundary" not in neo4j_out:
        raise RuntimeError(f"Faltan constraints esperados en Neo4j:\n{neo4j_out}")
    print("Neo4j OK -> constraints de :Activity y :Boundary verificados.")
    print("\n[OK] Etapa 2 verificada: Fase 1 operativa de extremo a extremo.")
