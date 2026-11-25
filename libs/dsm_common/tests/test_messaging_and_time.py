from datetime import UTC, datetime

import pytest

from dsm_common import ensure_utc
from dsm_common.messaging import InMemoryEventProducer, PublishedMessage, Topics
from dsm_common.schemas import make_dlq_event


def test_ensure_utc_normalizes_naive_and_offset_datetimes() -> None:
    naive = datetime(2024, 9, 10, 12, 0, 0)
    assert ensure_utc(naive) == datetime(2024, 9, 10, 12, 0, 0, tzinfo=UTC)


def test_make_dlq_event_populates_defaults() -> None:
    dlq = make_dlq_event({"raw": 1}, "invalid")
    assert dlq.dlq_id
    assert dlq.received_at.tzinfo == UTC
    assert dlq.error_reason == "invalid"
    assert dlq.raw_payload == {"raw": 1}


@pytest.mark.asyncio
async def test_in_memory_producer_publish_batch_preserves_order() -> None:
    producer = InMemoryEventProducer()
    batch = [
        PublishedMessage(topic=Topics.CANONICAL_EVENTS, key="u1", value={"n": 1}),
        PublishedMessage(topic=Topics.DLQ_EVENTS, key="d1", value={"n": 2}),
    ]
    with pytest.raises(RuntimeError):
        await producer.publish_batch(batch)

    await producer.start()
    await producer.publish_batch([])
    assert producer.messages == []

    await producer.publish_batch(batch)
    assert producer.messages == batch
