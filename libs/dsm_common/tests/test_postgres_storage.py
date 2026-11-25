from pathlib import Path

import pytest

from dsm_common.storage import InMemoryRunRepository, load_run_config_snapshot


def test_load_run_config_snapshot_reads_all_five_yamls() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    snapshot = load_run_config_snapshot(repo_root / "config")

    assert snapshot.hle_version == "v0.1-provisional"
    assert len(snapshot.hle_yaml_hash) == 64
    assert snapshot.hle_is_provisional is True
    assert len(snapshot.hle_rules_json) >= 6
    assert snapshot.clustering_algorithm == "denstream"
    assert snapshot.seed == 42
    assert snapshot.active_granularities == ["daily", "weekly", "monthly", "course"]
    assert snapshot.features_version == "v0.1-provisional"
    assert "total_events" in snapshot.features_list
    assert set(snapshot.raw_yaml_snapshot.keys()) == {
        "hle_catalog",
        "features",
        "windows",
        "clustering",
        "process_mining",
    }


@pytest.mark.asyncio
async def test_in_memory_run_repository_lifecycle() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    snapshot = load_run_config_snapshot(repo_root / "config")
    repo = InMemoryRunRepository()

    started = await repo.start_run(
        run_id="run_test_01",
        mode="stream",
        source_dataset="data/samples/sample_synthetic.jsonl",
        speed_factor="max",
        config_snapshot=snapshot,
    )
    assert started.status == "running"
    assert started.events_processed == 0
    assert "run_test_01" in repo.run_configs

    completed = await repo.complete_run("run_test_01", events_processed=80)
    assert completed.status == "completed"
    assert completed.events_processed == 80
    assert completed.finished_at is not None

    fetched = await repo.get_run("run_test_01")
    assert fetched is not None
    assert fetched.status == "completed"

    await repo.start_run(
        run_id="run_test_02",
        mode="stream",
        source_dataset="sample.jsonl",
        speed_factor="10x",
    )
    failed = await repo.fail_run("run_test_02", events_processed=12)
    assert failed.status == "failed"
    assert failed.events_processed == 12


@pytest.mark.asyncio
async def test_in_memory_run_repository_errors() -> None:
    repo = InMemoryRunRepository()
    await repo.start_run(
        run_id="dup_run",
        mode="stream",
        source_dataset="x.jsonl",
        speed_factor="max",
    )
    with pytest.raises(ValueError):
        await repo.start_run(
            run_id="dup_run",
            mode="stream",
            source_dataset="x.jsonl",
            speed_factor="max",
        )
    with pytest.raises(KeyError):
        await repo.complete_run("missing_run", events_processed=1)
    with pytest.raises(KeyError):
        await repo.fail_run("missing_run", events_processed=1)
