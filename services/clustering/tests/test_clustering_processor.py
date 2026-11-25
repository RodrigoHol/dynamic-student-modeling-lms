from datetime import UTC, datetime, timedelta
from pathlib import Path

from dsm_clustering.config import ClusteringServiceSettings
from dsm_clustering.processor import ClusteringServiceProcessor
from dsm_common.config import load_clustering_config
from dsm_common.messaging import InMemoryEventProducer, Topics
from dsm_common.schemas import FeatureVectorMessage
from dsm_common.storage import InMemoryProfileRepository
from dsm_core.clustering import ClusteringEngine

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_payload(u: str, window_id: str, total_events: float, regular: float) -> dict:
    now = datetime.now(UTC)
    msg = FeatureVectorMessage(
        run_id="run_svc_1",
        course_id="course_105",
        u=u,
        granularity="weekly",
        window_id=window_id,
        window_start=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 9, 9, 0, 0, tzinfo=UTC),
        features_version="v0.1-provisional",
        hle_version="v0.1-provisional",
        features={
            "total_events": total_events,
            "active_days": 5.0 if total_events > 10 else 1.0,
            "regularity_index": regular,
            "session_count": 6.0 if total_events > 10 else 1.0,
            "mean_session_duration_sec": 900.0 if total_events > 10 else 90.0,
        },
        event_count=int(total_events),
        last_event_ingested_at=now - timedelta(milliseconds=25),
        emitted_at=now,
    )
    return msg.model_dump(mode="json")


async def test_clustering_service_processor_persists_mongo_and_emits_assignments() -> None:
    cfg = load_clustering_config(REPO_ROOT / "config" / "clustering.yaml")
    engine = ClusteringEngine(cfg)
    repo = InMemoryProfileRepository()
    producer = InMemoryEventProducer()
    await producer.start()

    processor = ClusteringServiceProcessor(engine, repo, producer)

    for idx in range(12):
        payload = _make_payload(
            u=f"usr_{idx % 4}",
            window_id=f"2024-W{36 + (idx // 4)}",
            total_events=30.0 if idx % 2 == 0 else 3.0,
            regular=0.85 if idx % 2 == 0 else 0.15,
        )
        res = await processor.handle_raw_payload(payload)
        assert res is not None
        assert res.profile.latencies_ms.ingested_to_profile >= 0

    assert len(repo.profiles) == 12
    assert len(repo.snapshots) == 3
    assignment_msgs = [m for m in producer.messages if m.topic == Topics.ASSIGNMENTS]
    assert len(assignment_msgs) == 12
    assert assignment_msgs[0].key == "weekly:2024-W36"
    assert assignment_msgs[0].value["algorithm"] == "denstream"

    # Mensaje malformado se enruta a DLQ sin detener el procesador
    invalid_res = await processor.handle_raw_payload({"bad": "vector"})
    assert invalid_res is None
    dlq_msgs = [m for m in producer.messages if m.topic == Topics.DLQ_EVENTS]
    assert len(dlq_msgs) == 1

    await producer.stop()


async def test_clustering_service_switches_to_dbstream_via_config_only() -> None:
    base_cfg = load_clustering_config(REPO_ROOT / "config" / "clustering.yaml")
    db_cfg = base_cfg.model_copy(update={"algorithm": "dbstream"})
    engine = ClusteringEngine(db_cfg)
    repo = InMemoryProfileRepository()
    producer = InMemoryEventProducer()
    await producer.start()

    processor = ClusteringServiceProcessor(engine, repo, producer)
    res = await processor.handle_raw_payload(_make_payload("usr_1", "2024-W36", 25.0, 0.8))
    assert res is not None
    assert res.profile.clustering.algorithm == "dbstream"
    assert res.snapshot.algorithm == "dbstream"
    assert producer.messages[0].value["algorithm"] == "dbstream"

    settings = ClusteringServiceSettings()
    assert settings.clustering_metrics_port == 8005
    await producer.stop()
