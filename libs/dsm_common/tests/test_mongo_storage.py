from datetime import UTC, datetime

from dsm_common.schemas import (
    ClusteringResultMeta,
    ClusterSnapshotDocument,
    ExplainabilityFeature,
    ExplainabilityMeta,
    ProfileLatenciesMs,
    StudentProfileDocument,
)
from dsm_common.storage import InMemoryProfileRepository


async def test_in_memory_profile_repository_upsert_is_idempotent() -> None:
    repo = InMemoryProfileRepository()
    now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    start = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    end = datetime(2024, 9, 9, 0, 0, tzinfo=UTC)

    p1 = StudentProfileDocument(
        _id="r1:weekly:2024-W36:u1",
        run_id="r1",
        course_id="c1",
        student_id="u1",
        granularity="weekly",
        window_id="2024-W36",
        window_start=start,
        window_end=end,
        features_version="v0.1",
        features={"total_events": 5.0},
        clustering=ClusteringResultMeta(algorithm="denstream", cluster_id=0),
        explainability=ExplainabilityMeta(
            top_contributing_features=[ExplainabilityFeature(feature="total_events", z_score=0.5)]
        ),
        latencies_ms=ProfileLatenciesMs(ingested_to_profile=12),
        updated_at=now,
    )
    p2 = p1.model_copy(update={"features": {"total_events": 8.0}})

    snap = ClusterSnapshotDocument(
        _id="r1:weekly:2024-W36",
        run_id="r1",
        course_id="c1",
        granularity="weekly",
        window_id="2024-W36",
        window_start=start,
        window_end=end,
        algorithm="denstream",
        cluster_count=1,
        micro_cluster_count=1,
        centroids={"0": {"total_events": 6.5}},
        cluster_weights={"0": 2.0},
        snapshot={"cluster_count": 1},
        updated_at=now,
    )

    await repo.upsert_profile(p1)
    await repo.upsert_profile(p2)
    await repo.upsert_snapshot(snap)
    await repo.close()

    assert len(repo.profiles) == 1
    assert repo.profiles["r1:weekly:2024-W36:u1"].features["total_events"] == 8.0
    assert len(repo.snapshots) == 1
