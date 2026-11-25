"""Menú interactivo para verificar y demostrar las Fases 1, 2 y 3 desde terminal."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
from aiokafka import AIOKafkaConsumer

from dsm_common.config import AppSettings

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"
SYNTHETIC_DATASET = REPO_ROOT / "data" / "synthetic" / "synthetic_course_5000.jsonl"
PHASE3_DATASET = REPO_ROOT / "data" / "synthetic" / "phase3_determinism.jsonl"
PREPROCESSOR_URL = "http://localhost:8004"
VENV_SCRIPTS = REPO_ROOT / ".venv" / "Scripts"
PYTEST_BIN = VENV_SCRIPTS / "pytest.exe"
RUFF_BIN = VENV_SCRIPTS / "ruff.exe"
REPLAYER_BIN = VENV_SCRIPTS / "dsm-replayer.exe"

EXPECTED_PG_TABLES = {
    "courses",
    "experiment_metrics",
    "hle_catalog_versions",
    "resources",
    "run_configs",
    "runs",
    "users_roles",
}


def _print_header(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")


def _run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"El comando falló con código {result.returncode}: {' '.join(cmd)}")
    return result


def _run_capture(cmd: list[str]) -> str:
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"El comando falló con código {result.returncode}: {' '.join(cmd)}")
    return result.stdout


def _compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def stage_0_clean_all(*, auto_yes: bool = False) -> None:
    """Etapa 0: Limpia contenedores y volúmenes para partir desde cero."""
    _print_header("ETAPA 0 — Limpieza total (docker compose down -v)")
    if not auto_yes:
        answer = input(
            "Esto eliminará todos los contenedores y volúmenes locales de datos. "
            "¿Continuar? [s/N]: "
        ).strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Operación cancelada por el usuario.")
            return
    _run_cmd(_compose_cmd("down", "-v"))
    print("Limpieza completa finalizada.")


def stage_1_env_and_tests() -> None:
    """Etapa 1: Sincroniza dependencias (si uv está disponible) y corre pytest + ruff."""
    _print_header("ETAPA 1 — Entorno Python, pruebas unitarias y linter")
    if shutil.which("uv"):
        _run_cmd(["uv", "sync", "--all-packages"])
    else:
        print("Aviso: 'uv' no encontrado en PATH; se omite 'uv sync --all-packages'.")

    _run_cmd([str(PYTEST_BIN), "-v"])
    _run_cmd([str(RUFF_BIN), "check", "."])
    print("\n[OK] Etapa 1 verificada: pytest y ruff pasaron sin errores.")


async def _verify_phase1_gateway_and_pg(settings: AppSettings) -> None:
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


def stage_2_verify_phase1(settings: AppSettings) -> None:
    """Etapa 2: Levanta el stack Docker y valida Fase 1 (C2, Kafka, PostgreSQL, Mongo, Neo4j)."""
    _print_header("ETAPA 2 — Comprobación de Fase 1 (Infraestructura Kappa + C2 Gateway)")
    _run_cmd(_compose_cmd("up", "-d", "--wait"))
    _run_cmd(_compose_cmd("ps"))

    _run_cmd(
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

    asyncio.run(_verify_phase1_gateway_and_pg(settings))

    mongo_out = _run_capture(
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

    neo4j_out = _run_capture(
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


async def _verify_phase2_pg_and_kafka(settings: AppSettings, run_id: str) -> None:
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

    # En producción los consumidores quedan escuchando de forma continua; aquí leemos hasta
    # end_offsets con getmany(timeout_ms=2000) solo para finalizar la comprobación de prueba.
    consumer = AIOKafkaConsumer(
        "lms.events.canonical",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    await consumer.start()
    per_student_ts: dict[str, list[datetime]] = defaultdict(list)
    total_for_run = 0
    try:
        partitions = sorted(consumer.assignment(), key=lambda tp: tp.partition)
        if not partitions:
            raise RuntimeError("No se encontraron particiones asignadas en lms.events.canonical.")
        await consumer.seek_to_beginning(*partitions)
        end_offsets = await consumer.end_offsets(partitions)

        while True:
            positions = {tp: await consumer.position(tp) for tp in partitions}
            if all(positions[tp] >= end_offsets[tp] for tp in partitions):
                break
            batches = await consumer.getmany(timeout_ms=2000)
            if not batches:
                break
            for records in batches.values():
                for msg in records:
                    ev = msg.value
                    if ev.get("run_id") == run_id and ev.get("event_type") != "run_eof":
                        total_for_run += 1
                        per_student_ts[ev["u"]].append(datetime.fromisoformat(ev["t"]))
    finally:
        await consumer.stop()

    out_of_order = sum(1 for ts_list in per_student_ts.values() if ts_list != sorted(ts_list))
    print(
        f"Kafka lms.events.canonical -> total={total_for_run} | "
        f"estudiantes={len(per_student_ts)} | fuera_de_orden={out_of_order}"
    )
    if total_for_run != 5000 or len(per_student_ts) != 50 or out_of_order != 0:
        raise RuntimeError(
            f"Verificación Kafka fallida (total={total_for_run}, "
            f"estudiantes={len(per_student_ts)}, fuera_de_orden={out_of_order})."
        )


def stage_3_verify_phase2(settings: AppSettings) -> None:
    """Etapa 3: Genera 5,000 eventos sintéticos, ejecuta replay y valida PostgreSQL + Kafka."""
    _print_header("ETAPA 3 — Comprobación de Fase 2 (Generador sintético + C3 Replayer)")
    _run_cmd(
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
    _run_cmd(
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

    asyncio.run(_verify_phase2_pg_and_kafka(settings, run_id))
    print(f"\n[OK] Etapa 3 verificada: 5,000 eventos validados en PostgreSQL y Kafka ({run_id}).")


def stage_4_verify_phase3(settings: AppSettings) -> None:
    """Etapa 4: Verifica C4 Preprocessor y prueba de determinismo 10x vs max."""
    _print_header("ETAPA 4 — Comprobación de Fase 3 (C4 Preprocessor + Determinismo 10x vs max)")

    async def _check_c4_health() -> None:
        async with httpx.AsyncClient(base_url=PREPROCESSOR_URL, timeout=10.0) as client:
            resp = await client.get("/health")
            if resp.status_code != 200 or resp.json().get("status") != "ok":
                raise RuntimeError(f"Healthcheck inválido en C4 Preprocessor: {resp.text}")
            print(f"C4 /health -> {resp.status_code} {resp.json()}")

    asyncio.run(_check_c4_health())

    _run_cmd(
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

    _run_cmd(
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
    _run_cmd(
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

    asyncio.run(_verify_phase3_determinism(settings, run_10x, run_max))
    print(
        f"\n[OK] Etapa 4 verificada: determinismo 100% entre {run_10x} (10x) y {run_max} (max)."
    )


async def _collect_topic_records(
    bootstrap_servers: str,
    topic: str,
    target_run_ids: set[str],
) -> list[dict]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    await consumer.start()
    collected: list[dict] = []
    try:
        partitions = sorted(consumer.assignment(), key=lambda tp: tp.partition)
        if not partitions:
            raise RuntimeError(f"No se encontraron particiones asignadas en {topic}.")
        await consumer.seek_to_beginning(*partitions)
        end_offsets = await consumer.end_offsets(partitions)
        while True:
            positions = {tp: await consumer.position(tp) for tp in partitions}
            if all(positions[tp] >= end_offsets[tp] for tp in partitions):
                break
            batches = await consumer.getmany(timeout_ms=2000)
            if not batches:
                break
            for records in batches.values():
                for msg in records:
                    val = msg.value
                    if isinstance(val, dict) and val.get("run_id") in target_run_ids:
                        collected.append(val)
    finally:
        await consumer.stop()
    return collected


async def _verify_phase3_determinism(
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

    feat_records: list[dict] = []
    trace_records: list[dict] = []
    while loop.time() < deadline:
        feat_records = await _collect_topic_records(
            settings.kafka_bootstrap_servers,
            "analytics.features",
            target_runs,
        )
        trace_records = await _collect_topic_records(
            settings.kafka_bootstrap_servers,
            "analytics.traces",
            target_runs,
        )
        course_feats_10x = {
            r["u"] for r in feat_records if r["run_id"] == run_10x and r["granularity"] == "course"
        }
        course_feats_max = {
            r["u"] for r in feat_records if r["run_id"] == run_max and r["granularity"] == "course"
        }
        course_traces_10x = {
            r["u"]
            for r in trace_records
            if r["run_id"] == run_10x and r["granularity"] == "course"
        }
        course_traces_max = {
            r["u"]
            for r in trace_records
            if r["run_id"] == run_max and r["granularity"] == "course"
        }
        if (
            len(course_feats_10x) >= expected_students
            and len(course_feats_max) >= expected_students
            and len(course_traces_10x) >= expected_students
            and len(course_traces_max) >= expected_students
        ):
            break
        await asyncio.sleep(1.0)

    def _normalize_features(run_id: str) -> dict[tuple[str, str, str], dict]:
        result: dict[tuple[str, str, str], dict] = {}
        for rec in feat_records:
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

    def _normalize_traces(run_id: str) -> dict[tuple[str, str, str], dict]:
        result: dict[tuple[str, str, str], dict] = {}
        for rec in trace_records:
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

    feats_10x = _normalize_features(run_10x)
    feats_max = _normalize_features(run_max)
    traces_10x = _normalize_traces(run_10x)
    traces_max = _normalize_traces(run_max)

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
        item
        for rec in traces_10x.values()
        for item in rec["trace"]
        if item[4] == "report"
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


def stage_5_stop_stack() -> None:
    """Etapa 5: Apaga los contenedores Docker conservando los volúmenes de datos."""
    _print_header("ETAPA 5 — Apagar stack Docker (conservando volúmenes)")
    _run_cmd(_compose_cmd("down"))
    print("Contenedores detenidos.")


def show_status(settings: AppSettings) -> None:
    """Muestra el estado actual de los contenedores y enlaces útiles para demostración."""
    _print_header("Estado de contenedores e interfaces web")
    _run_cmd(_compose_cmd("ps"), check=False)
    print("\nInterfaces web locales para demostración:")
    print(f"  - Swagger / OpenAPI (C2 Gateway): {settings.gateway_url.rstrip('/')}/docs")
    print(f"  - C4 Preprocessor (/health):      {PREPROCESSOR_URL}/health")
    print("  - Redpanda Console (Kafka):       http://localhost:8080")
    print("  - Neo4j Browser (Grafos):         http://localhost:7474")


def _render_menu(statuses: dict[str, str]) -> None:
    print("\n" + "=" * 72)
    print("  CONTROL DE AVANCE Y DEMOSTRACIÓN — DYNAMIC STUDENT MODELING LMS")
    print("=" * 72)
    print(f"  [0] Limpieza total desde cero (down -v)               [{statuses['0']}]")
    print(f"  [1] Etapa 1: Entorno, pytest y ruff                   [{statuses['1']}]")
    print(f"  [2] Etapa 2: Comprobar Fase 1 (Docker + C2 + 3 BDs)   [{statuses['2']}]")
    print(f"  [3] Etapa 3: Comprobar Fase 2 (5,000 ev C3 -> Kafka)  [{statuses['3']}]")
    print(f"  [4] Etapa 4: Comprobar Fase 3 (C4 + 10x vs max)       [{statuses['4']}]")
    print(f"  [5] Etapa 5: Apagar stack Docker (down)               [{statuses['5']}]")
    print("  [a] Ejecutar demostración completa (Etapas 1 -> 2 -> 3 -> 4)")
    print("  [s] Ver estado de contenedores e interfaces web")
    print("  [q] Salir")
    print("-" * 72)


def _execute_choice(
    choice: str,
    settings: AppSettings,
    statuses: dict[str, str],
    *,
    auto_yes: bool = False,
) -> bool:
    """Ejecuta una opción del menú. Devuelve `False` si el usuario eligió salir."""
    normalized = choice.strip().lower()
    if normalized == "q":
        return False

    actions = {
        "0": lambda: stage_0_clean_all(auto_yes=auto_yes),
        "1": stage_1_env_and_tests,
        "2": lambda: stage_2_verify_phase1(settings),
        "3": lambda: stage_3_verify_phase2(settings),
        "4": lambda: stage_4_verify_phase3(settings),
        "5": stage_5_stop_stack,
    }

    if normalized == "s":
        show_status(settings)
        return True

    if normalized == "a":
        for key in ("1", "2", "3", "4"):
            try:
                actions[key]()
                statuses[key] = "OK"
            except Exception as exc:
                statuses[key] = "Error"
                print(f"\n[ERROR] Falló la etapa {key}: {exc}")
                return True
        print("\n[OK] Demostración completa (Etapas 1 -> 2 -> 3 -> 4) finalizada con éxito.")
        return True

    if normalized in actions:
        try:
            actions[normalized]()
            statuses[normalized] = "OK"
        except Exception as exc:
            statuses[normalized] = "Error"
            print(f"\n[ERROR] Falló la etapa {normalized}: {exc}")
        return True

    print(f"Opción no válida: '{choice}'.")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Menú interactivo para verificar y demostrar las Fases 1, 2 y 3."
    )
    parser.add_argument(
        "--step",
        choices=["0", "1", "2", "3", "4", "5", "all", "status"],
        default=None,
        help="Ejecuta una etapa directamente sin abrir el menú interactivo.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma automáticamente operaciones destructivas (como la Etapa 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = AppSettings()
    statuses = {
        "0": "Pendiente",
        "1": "Pendiente",
        "2": "Pendiente",
        "3": "Pendiente",
        "4": "Pendiente",
        "5": "-",
    }

    if args.step is not None:
        mapped = {"all": "a", "status": "s"}.get(args.step, args.step)
        _execute_choice(mapped, settings, statuses, auto_yes=args.yes)
        if any(val == "Error" for val in statuses.values()):
            return 1
        return 0

    while True:
        _render_menu(statuses)
        try:
            choice = input("Selecciona una opción: ")
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo del menú.")
            break
        if not _execute_choice(choice, settings, statuses, auto_yes=args.yes):
            print("Hasta luego.")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
