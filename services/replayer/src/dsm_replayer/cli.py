from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import click

from dsm_common.config import AppSettings
from dsm_common.storage import PostgresRunRepository, RunConfigSnapshot, load_run_config_snapshot
from dsm_replayer.generator import (
    SyntheticCourseConfig,
    generate_synthetic_events,
    write_synthetic_dataset,
)
from dsm_replayer.parsers import create_parser, detect_format
from dsm_replayer.parsers.base import parse_datetime_utc
from dsm_replayer.scheduler import ReplayDispatcher, ReplayStats, parse_speed_factor


def generate_run_id(now: datetime | None = None) -> str:
    ts = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_{uuid4().hex[:6]}"


async def _execute_replay(
    *,
    dataset_path: Path,
    fmt: str,
    speed_raw: str,
    gateway_url: str,
    run_id: str,
    course_id: str | None,
    batch_size: int,
    max_delay: float | None,
    limit: int | None,
    postgres_dsn: str,
    config_dir: Path,
    use_db: bool,
    emit_eof: bool,
) -> ReplayStats:
    speed = parse_speed_factor(speed_raw)
    parser = create_parser(fmt, course_id=course_id)
    repo = PostgresRunRepository(postgres_dsn) if use_db else None

    config_snapshot: RunConfigSnapshot | None = None
    if use_db and config_dir.is_dir():
        config_snapshot = load_run_config_snapshot(config_dir)

    dispatcher = ReplayDispatcher(
        gateway_url=gateway_url,
        run_repository=repo,
        batch_size=batch_size,
    )
    try:
        return await dispatcher.replay(
            parser.parse_stream(dataset_path),
            run_id=run_id,
            source_dataset=str(dataset_path),
            format_name=parser.format_name,
            speed=speed,
            config_snapshot=config_snapshot,
            max_delay_seconds=max_delay,
            limit=limit,
            emit_eof=emit_eof,
        )
    finally:
        if repo is not None:
            await repo.close()


@click.group()
def main() -> None:
    pass


@main.command()
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["synthetic_jsonl", "moodle_csv", "moodle_db"], case_sensitive=False),
    default="synthetic_jsonl",
    show_default=True,
    help="Formato del archivo generado.",
)
@click.option("--students", type=int, default=50, show_default=True, help="Número de estudiantes.")
@click.option(
    "--weeks",
    type=int,
    default=8,
    show_default=True,
    help="Duración del curso en semanas.",
)
@click.option(
    "--target-events",
    type=int,
    default=None,
    help="Cantidad exacta de eventos a generar (opcional).",
)
@click.option("--seed", type=int, default=42, show_default=True, help="Semilla aleatoria.")
@click.option(
    "--course-id",
    default="course_105",
    show_default=True,
    help="Identificador del curso.",
)
@click.option(
    "--start-date",
    default="2024-09-02T08:00:00Z",
    show_default=True,
    help="Fecha de inicio ISO-8601 UTC.",
)
@click.option(
    "--noise-ratio",
    type=float,
    default=0.02,
    show_default=True,
    help="Proporción de ruido operativo (0.0 a 1.0).",
)
def generate(
    output_path: Path,
    fmt: str,
    students: int,
    weeks: int,
    target_events: int | None,
    seed: int,
    course_id: str,
    start_date: str,
    noise_ratio: float,
) -> None:
    config = SyntheticCourseConfig(
        num_students=students,
        num_weeks=weeks,
        seed=seed,
        course_id=course_id,
        start_date=parse_datetime_utc(start_date),
        target_events=target_events,
        noise_ratio=noise_ratio,
    )
    events = generate_synthetic_events(config)
    count = write_synthetic_dataset(events, output_path, fmt=fmt.lower())
    click.echo(
        f"Dataset generado: {output_path} | formato={fmt.lower()} | eventos={count} "
        f"| estudiantes={students} | semanas={weeks} | seed={seed}"
    )


@main.command()
@click.argument("dataset_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["moodle_csv", "moodle_db", "synthetic_jsonl"], case_sensitive=False),
    default=None,
    help="Formato de entrada (autodetectado si se omite).",
)
@click.option(
    "--speed",
    default="max",
    show_default=True,
    help="Factor de velocidad ('1x', '10x', '100x' o 'max').",
)
@click.option(
    "--gateway-url",
    default=None,
    help="URL base de C2 Ingestion Gateway (por defecto DSM_GATEWAY_URL).",
)
@click.option("--run-id", default=None, help="Identificador de corrida (autogenerado si se omite).")
@click.option("--course-id", default=None, help="Curso por defecto si el origen no lo incluye.")
@click.option(
    "--batch-size",
    type=int,
    default=100,
    show_default=True,
    help="Tamaño de lote en modo max.",
)
@click.option(
    "--max-delay",
    type=float,
    default=None,
    help="Tope máximo en segundos de pausa entre eventos en modo temporizado.",
)
@click.option("--limit", type=int, default=None, help="Límite máximo de eventos a reproducir.")
@click.option(
    "--postgres-dsn",
    default=None,
    help="DSN de PostgreSQL (por defecto DSM_POSTGRES_DSN).",
)
@click.option(
    "--config-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directorio con los YAML de configuración (por defecto DSM_CONFIG_DIR).",
)
@click.option(
    "--no-db",
    is_flag=True,
    default=False,
    help="Omite el registro de corrida en PostgreSQL.",
)
@click.option(
    "--emit-eof / --no-emit-eof",
    default=True,
    show_default=True,
    help="Emite señal de fin de corrida (EOF) hacia C2 al concluir el replay.",
)
def replay(
    dataset_path: Path,
    fmt: str | None,
    speed: str,
    gateway_url: str | None,
    run_id: str | None,
    course_id: str | None,
    batch_size: int,
    max_delay: float | None,
    limit: int | None,
    postgres_dsn: str | None,
    config_dir: Path | None,
    no_db: bool,
    emit_eof: bool,
) -> None:
    settings = AppSettings()
    resolved_fmt = fmt.lower() if fmt is not None else detect_format(dataset_path)
    resolved_run_id = run_id or generate_run_id()
    resolved_gateway = gateway_url or settings.gateway_url
    resolved_dsn = postgres_dsn or settings.postgres_dsn
    resolved_config_dir = config_dir or settings.config_dir

    stats = asyncio.run(
        _execute_replay(
            dataset_path=dataset_path,
            fmt=resolved_fmt,
            speed_raw=speed,
            gateway_url=resolved_gateway,
            run_id=resolved_run_id,
            course_id=course_id,
            batch_size=batch_size,
            max_delay=max_delay,
            limit=limit,
            postgres_dsn=resolved_dsn,
            config_dir=resolved_config_dir,
            use_db=not no_db,
            emit_eof=emit_eof,
        )
    )
    db_status = "omitido (--no-db)" if no_db else "completed (PostgreSQL)"
    click.echo(
        f"Replay finalizado | run_id={stats.run_id} | formato={stats.format_name} "
        f"| velocidad={stats.speed_factor} | total={stats.total_events} "
        f"| aceptados={stats.accepted_events} | dlq={stats.dlq_events} "
        f"| duracion={stats.elapsed_seconds:.3f}s | throughput={stats.throughput_eps:.1f} ev/s "
        f"| db={db_status}"
    )


if __name__ == "__main__":
    main()
