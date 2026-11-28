from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo
from dsm_common.storage import InMemoryRunRepository
from dsm_experiments.runners import run_in_memory_benchmark

REPO_ROOT = Path(__file__).resolve().parents[2]


def _synthetic_canonical_events() -> list[CanonicalEvent]:
    base = datetime(2024, 9, 2, 9, 0, tzinfo=UTC)
    events: list[CanonicalEvent] = []
    idx = 0
    for week in range(2):
        for stu in range(12):
            u = f"usr_{stu:02d}"
            # Dos arquetipos diferenciados: activos vs rezagados
            is_high = stu < 6
            actions = (
                ["ACCESO_CURSO", "CONSULTA_RECURSO", "PARTICIPACION_FORO", "ENVIO_TAREA"]
                if is_high
                else ["ACCESO_CURSO", "CONSULTA_RECURSO"]
            )
            reps = 3 if is_high else 1
            for r_idx in range(reps):
                for a_idx, hle in enumerate(actions):
                    comp = {
                        "ACCESO_CURSO": ("core", "viewed", "course"),
                        "CONSULTA_RECURSO": ("mod_resource", "viewed", "resource"),
                        "PARTICIPACION_FORO": ("mod_forum", "created", "post"),
                        "ENVIO_TAREA": ("mod_assign", "submitted", "assign"),
                    }[hle]
                    t = base + timedelta(
                        days=week * 7 + (r_idx % 3),
                        hours=a_idx + (stu % 3),
                        minutes=r_idx * 15,
                    )
                    events.append(
                        CanonicalEvent(
                            event_id=f"ev_{idx:05d}",
                            run_id="exp_test_01",
                            u=u,
                            a=comp[1],
                            r=ResourceInfo(
                                resource_id=f"res_{a_idx}",
                                resource_type=comp[2],
                                name=f"Recurso {a_idx}",
                            ),
                            t=t,
                            ingested_at=t,
                            M=EventMetadata(
                                course_id="course_105",
                                source_format="synthetic_jsonl",
                                component=comp[0],
                            ),
                        )
                    )
                    idx += 1
    return events


@pytest.mark.asyncio
async def test_in_memory_benchmark_runs_stream_vs_batch_and_exports(tmp_path: Path) -> None:
    events = _synthetic_canonical_events()
    repo = InMemoryRunRepository()
    out_dir = tmp_path / "exp_out"

    report = await run_in_memory_benchmark(
        events,
        config_dir=REPO_ROOT / "config",
        dataset_label="synthetic_unit_test",
        experiment_id="exp_unit",
        n_clusters_batch=2,
        run_repository=repo,
        output_dir=out_dir,
    )

    assert report.events_count == len(events)
    assert report.windows_count > 0
    methods = {row.method for row in report.rows}
    assert methods == {"batch_kmeans", "stream_denstream", "stream_dbstream"}

    # Reproducibilidad determinista exacta (ARI == 1.0)
    den_rows = [
        r
        for r in report.rows
        if r.method == "stream_denstream" and r.ari_reproducibility is not None
    ]
    assert den_rows
    assert all(r.ari_reproducibility == pytest.approx(1.0) for r in den_rows)

    # Fitness y Precision en [0, 1]
    assert any(r.pm_fitness is not None and 0.0 <= r.pm_fitness <= 1.0 for r in report.rows)
    assert any(r.pm_precision is not None and 0.0 <= r.pm_precision <= 1.0 for r in report.rows)

    # Persistencia en RunRepository
    assert len(repo.runs) == 3
    assert len(repo.experiment_metrics) == len(report.rows)

    # Exportación de archivos para la tesis
    for filename in (
        "metrics_summary.csv",
        "comparison_table.tex",
        "summary.json",
        "comparison_metrics.png",
    ):
        fpath = out_dir / filename
        assert fpath.is_file()
        assert fpath.stat().st_size > 0
