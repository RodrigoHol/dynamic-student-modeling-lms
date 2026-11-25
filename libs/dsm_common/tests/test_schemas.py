from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dsm_common.schemas import (
    CanonicalEvent,
    ClusterAssignmentMessage,
    ClusteringResultMeta,
    ClusterSnapshotDocument,
    DlqEvent,
    EventMetadata,
    ExplainabilityFeature,
    ExplainabilityMeta,
    FeatureVectorMessage,
    ProfileLatenciesMs,
    RawEventInput,
    ResourceInfo,
    RunEofEvent,
    StudentProfileDocument,
    TraceEventItem,
    TraceMessage,
)


def test_raw_event_normalizes_naive_timestamp_to_utc() -> None:
    raw = RawEventInput(
        raw_user_id="alu_001",
        action="submitted",
        resource=ResourceInfo(resource_id="assign_1", resource_type="assign", name="Tarea 1"),
        timestamp=datetime(2024, 9, 18, 14, 23, 11),
        metadata=EventMetadata(course_id="course_105", source_format="moodle_csv"),
    )
    assert raw.timestamp.tzinfo == UTC


def test_raw_event_rejects_blank_fields() -> None:
    with pytest.raises(ValidationError):
        RawEventInput(
            raw_user_id="   ",
            action="viewed",
            resource=ResourceInfo(resource_id="res_1", resource_type="page"),
            timestamp=datetime.now(UTC),
            metadata=EventMetadata(course_id="course_105"),
        )


def test_canonical_and_dlq_serialization() -> None:
    now = datetime.now(UTC)
    canonical = CanonicalEvent(
        event_id="evt-1",
        run_id="run_001",
        u="usr_abcdef1234567890",
        a="viewed",
        r=ResourceInfo(resource_id="res_1", resource_type="resource"),
        t=now,
        ingested_at=now,
        M=EventMetadata(course_id="course_105", extra_field="ok"),
    )
    dumped = canonical.model_dump(mode="json")
    assert dumped["u"] == "usr_abcdef1234567890"
    assert dumped["M"]["extra_field"] == "ok"

    dlq = DlqEvent(
        dlq_id="dlq-1",
        received_at=now,
        error_reason="invalid field",
        raw_payload={"bad": True},
    )
    assert dlq.raw_payload == {"bad": True}


def test_analytics_and_eof_schemas_normalize_utc() -> None:
    naive_start = datetime(2024, 9, 2, 0, 0, 0)
    naive_end = datetime(2024, 9, 3, 0, 0, 0)
    naive_now = datetime(2024, 9, 3, 0, 5, 0)

    fv = FeatureVectorMessage(
        run_id="run_001",
        course_id="course_105",
        u="usr_abcdef1234567890",
        granularity="daily",
        window_id="2024-09-02",
        window_start=naive_start,
        window_end=naive_end,
        features_version="v0.1-provisional",
        hle_version="v0.1-provisional",
        features={"total_events": 4.0, "active_days": 1.0},
        event_count=4,
        last_event_ingested_at=naive_now,
        emitted_at=naive_now,
    )
    assert fv.window_start.tzinfo == UTC
    assert fv.window_end.tzinfo == UTC
    assert fv.last_event_ingested_at.tzinfo == UTC
    assert fv.emitted_at.tzinfo == UTC

    trace_msg = TraceMessage(
        run_id="run_001",
        course_id="course_105",
        u="usr_abcdef1234567890",
        granularity="daily",
        window_id="2024-09-02",
        window_start=naive_start,
        window_end=naive_end,
        hle_version="v0.1-provisional",
        trace=[
            TraceEventItem(
                event_id="evt-1",
                hle="ACCESO_CURSO",
                t=naive_start,
                a="viewed",
                resource_id="course_105",
                resource_type="course",
            )
        ],
        event_count=1,
        last_event_ingested_at=naive_now,
        emitted_at=naive_now,
    )
    assert trace_msg.trace[0].t.tzinfo == UTC

    eof = RunEofEvent(
        event_id="eof-1",
        run_id="run_001",
        u="usr_abcdef1234567890",
        course_id="course_105",
        emitted_at=naive_now,
    )
    assert eof.event_type == "run_eof"
    assert eof.emitted_at.tzinfo == UTC


def test_clustering_schemas_and_mongo_docs() -> None:
    naive_start = datetime(2024, 9, 2, 0, 0, 0)
    naive_end = datetime(2024, 9, 9, 0, 0, 0)
    naive_now = datetime(2024, 9, 9, 0, 5, 0)

    profile = StudentProfileDocument(
        _id="run_1:weekly:2024-W36:usr_1",
        run_id="run_1",
        course_id="course_105",
        student_id="usr_1",
        granularity="weekly",
        window_id="2024-W36",
        window_start=naive_start,
        window_end=naive_end,
        features_version="v0.1-provisional",
        features={"total_events": 12.0},
        clustering=ClusteringResultMeta(
            algorithm="denstream",
            cluster_id=1,
            previous_cluster_id=0,
            transition_detected=True,
            distance_to_centroid=0.45,
            is_outlier=False,
        ),
        explainability=ExplainabilityMeta(
            top_contributing_features=[ExplainabilityFeature(feature="total_events", z_score=1.2)]
        ),
        latencies_ms=ProfileLatenciesMs(ingested_to_profile=18),
        updated_at=naive_now,
    )
    mongo_doc = profile.to_mongo_doc()
    assert mongo_doc["_id"] == "run_1:weekly:2024-W36:usr_1"
    assert mongo_doc["window_start"].tzinfo == UTC
    assert mongo_doc["updated_at"].tzinfo == UTC

    snapshot = ClusterSnapshotDocument(
        _id="run_1:weekly:2024-W36",
        run_id="run_1",
        course_id="course_105",
        granularity="weekly",
        window_id="2024-W36",
        window_start=naive_start,
        window_end=naive_end,
        algorithm="denstream",
        cluster_count=2,
        micro_cluster_count=3,
        centroids={"1": {"total_events": 10.0}},
        cluster_weights={"1": 4.0},
        snapshot={"cluster_count": 2},
        updated_at=naive_now,
    )
    assert snapshot.to_mongo_doc()["_id"] == "run_1:weekly:2024-W36"

    assignment = ClusterAssignmentMessage(
        run_id="run_1",
        course_id="course_105",
        u="usr_1",
        granularity="weekly",
        window_id="2024-W36",
        window_start=naive_start,
        window_end=naive_end,
        algorithm="denstream",
        cluster_id=1,
        previous_cluster_id=0,
        transition_detected=True,
        distance_to_centroid=0.45,
        is_outlier=False,
        last_event_ingested_at=naive_now,
        emitted_at=naive_now,
    )
    assert assignment.last_event_ingested_at.tzinfo == UTC
    assert assignment.emitted_at.tzinfo == UTC
