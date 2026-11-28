from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dsm_common.config import AppSettings
from dsm_common.storage import PostgresRunRepository
from dsm_experiments.runners import (
    evaluate_live_run,
    load_canonical_events_from_jsonl,
    run_in_memory_benchmark,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsm-experiments",
        description="C9 Experiment Runner: línea base batch, métricas y exportación para la tesis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser(
        "benchmark",
        help="Ejecuta comparativa stream (DenStream/DBSTREAM) vs batch (K-Means + PM4Py).",
    )
    bench.add_argument("dataset", type=Path, help="Archivo JSONL (crudo sintético o canónico).")
    bench.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/latest"),
        help="Directorio de salida para CSV, LaTeX, JSON y figura PNG.",
    )
    bench.add_argument(
        "--experiment-id",
        default=None,
        help="Identificador opcional del experimento.",
    )
    bench.add_argument(
        "--n-clusters",
        type=int,
        default=4,
        help="Número de clústeres para K-Means.",
    )
    bench.add_argument(
        "--no-pg",
        action="store_true",
        help="No persiste métricas en PostgreSQL (modo offline en memoria).",
    )

    eval_cmd = sub.add_parser(
        "evaluate-run",
        help="Evalúa una corrida en vivo en MongoDB/PostgreSQL frente al baseline batch.",
    )
    eval_cmd.add_argument("run_id", help="ID de la corrida en vivo a evaluar.")
    eval_cmd.add_argument("--dataset", type=Path, required=True, help="Dataset JSONL original.")
    eval_cmd.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results/live"),
        help="Directorio de salida para reportes exportados.",
    )
    eval_cmd.add_argument("--n-clusters", type=int, default=4, help="K para K-Means batch.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = AppSettings()

    if args.command == "benchmark":
        events = load_canonical_events_from_jsonl(
            args.dataset,
            salt=settings.pseudonym_salt,
            run_id=args.experiment_id or "exp_benchmark",
        )
        pg_repo = None if args.no_pg else PostgresRunRepository(settings.postgres_dsn)

        async def _run_bench() -> None:
            try:
                report = await run_in_memory_benchmark(
                    events,
                    config_dir=settings.config_dir,
                    dataset_label=str(args.dataset),
                    experiment_id=args.experiment_id,
                    n_clusters_batch=args.n_clusters,
                    run_repository=pg_repo,
                    output_dir=args.output_dir,
                )
            finally:
                if pg_repo is not None:
                    await pg_repo.close()

            print(
                f"Benchmark {report.experiment_id} completado: {report.events_count} eventos | "
                f"{report.windows_count} ventanas | reportes en {args.output_dir}"
            )
            for summary in report.method_summaries:
                if summary.granularity == "all":
                    print(
                        f"  - {summary.method:16s} | sil={summary.mean_silhouette} | "
                        f"ari_batch={summary.mean_ari_vs_batch} | "
                        f"ari_reprod={summary.mean_ari_reproducibility} | "
                        f"fit={summary.mean_pm_fitness} | prec={summary.mean_pm_precision} | "
                        f"tp={summary.throughput_eps} vec/s"
                    )

        asyncio.run(_run_bench())
        return 0

    if args.command == "evaluate-run":
        records = asyncio.run(
            evaluate_live_run(
                run_id=args.run_id,
                dataset_path=args.dataset,
                settings=settings,
                n_clusters_batch=args.n_clusters,
                output_dir=args.output_dir,
            )
        )
        print(
            f"Evaluación completada para '{args.run_id}': "
            f"{len(records)} registros guardados en experiment_metrics."
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
