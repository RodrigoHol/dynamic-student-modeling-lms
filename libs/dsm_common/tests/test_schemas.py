from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dsm_common.schemas import CanonicalEvent, DlqEvent, EventMetadata, RawEventInput, ResourceInfo


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
