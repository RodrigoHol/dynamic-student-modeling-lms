from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dsm_experiments.runners.experiment_runner import BenchmarkReport


def _fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "--"
    return f"{value:.{digits}f}"


def export_benchmark_reports(report: BenchmarkReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "metrics_summary.csv"
    tex_path = output_dir / "comparison_table.tex"
    json_path = output_dir / "summary.json"
    png_path = output_dir / "comparison_metrics.png"

    fieldnames = [
        "method",
        "granularity",
        "window_id",
        "student_count",
        "cluster_count",
        "silhouette_score",
        "ari_vs_batch",
        "ari_reproducibility",
        "pm_fitness",
        "pm_precision",
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "throughput_eps",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.rows:
            writer.writerow(row.model_dump())

    tex_lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\caption{Comparativa cuantitativa entre modelado en flujo y línea base batch.}",
        "\\label{tab:stream-vs-batch}",
        "\\begin{tabular}{llrrrrrrr}",
        "\\hline",
        (
            "Método & Granularidad & Silueta & ARI vs Batch & ARI Reprod. & "
            "Fitness & Precision & p95 (ms) & Throughput (ev/s) \\\\"
        ),
        "\\hline",
    ]
    for agg in report.method_summaries:
        tex_lines.append(
            f"{agg.method.replace('_', '\\_')} & {agg.granularity} & "
            f"{_fmt(agg.mean_silhouette)} & {_fmt(agg.mean_ari_vs_batch)} & "
            f"{_fmt(agg.mean_ari_reproducibility)} & {_fmt(agg.mean_pm_fitness)} & "
            f"{_fmt(agg.mean_pm_precision)} & {_fmt(agg.p95_latency_ms, 2)} & "
            f"{_fmt(agg.throughput_eps, 1)} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", "\\end{table}"])
    tex_path.write_text("\n".join(tex_lines) + "\n", encoding="utf-8")

    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    course_summaries = [s for s in report.method_summaries if s.granularity == "all"]
    if not course_summaries:
        course_summaries = report.method_summaries

    methods = [s.method for s in course_summaries]
    metric_pairs = [
        ("Silueta", [s.mean_silhouette or 0.0 for s in course_summaries]),
        ("ARI vs Batch", [s.mean_ari_vs_batch or 0.0 for s in course_summaries]),
        ("PM Fitness", [s.mean_pm_fitness or 0.0 for s in course_summaries]),
        ("PM Precision", [s.mean_pm_precision or 0.0 for s in course_summaries]),
    ]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    if methods:
        x_positions = list(range(len(methods)))
        width = 0.18
        for idx, (label, values) in enumerate(metric_pairs):
            offset = (idx - 1.5) * width
            ax.bar([x + offset for x in x_positions], values, width=width, label=label)
        ax.set_xticks(x_positions)
        ax.set_xticklabels(methods)
    ax.set_ylim(-0.2, 1.1)
    ax.set_ylabel("Puntuación")
    ax.set_title("Comparativa Stream vs. Batch (Métricas de Calidad y Proceso)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)

    # Validar JSON generado
    json.loads(json_path.read_text(encoding="utf-8"))

    return {
        "csv": csv_path,
        "tex": tex_path,
        "json": json_path,
        "png": png_path,
    }
