from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from dsm_common.config import AppSettings
from dsm_common.messaging import InMemoryEventProducer, Topics
from dsm_gateway.main import create_app


def _sample_valid_event(raw_user_id: str = "student_42") -> dict:
    return {
        "raw_user_id": raw_user_id,
        "action": "submitted",
        "resource": {
            "resource_id": "assign_10",
            "resource_type": "assign",
            "name": "Tarea 1",
        },
        "timestamp": "2024-09-18T14:23:11Z",
        "metadata": {
            "course_id": "course_105",
            "source_format": "moodle_csv",
            "component": "mod_assign",
            "raw_eventname": "\\mod_assign\\event\\assessable_submitted",
        },
    }


@asynccontextmanager
async def _build_client() -> AsyncIterator[tuple[httpx.AsyncClient, InMemoryEventProducer]]:
    producer = InMemoryEventProducer()
    settings = AppSettings(pseudonym_salt="test-salt-value", default_run_id="run_test_001")
    app = create_app(producer=producer, settings=settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, producer


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    async with _build_client() as (client, _):
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "ingestion-gateway"}


@pytest.mark.asyncio
async def test_ingest_valid_event_pseudonymizes_and_publishes_canonical() -> None:
    async with _build_client() as (client, producer):
        resp = await client.post("/api/v1/events", json=_sample_valid_event("alu_999"))

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["run_id"] == "run_test_001"
    assert body["u"].startswith("usr_")
    assert body["u"] != "alu_999"
    assert "ingested_at" in body

    assert len(producer.messages) == 1
    msg = producer.messages[0]
    assert msg.topic == Topics.CANONICAL_EVENTS
    assert msg.key == body["u"]
    assert msg.value["u"] == body["u"]
    assert msg.value["a"] == "submitted"
    assert "raw_user_id" not in msg.value


@pytest.mark.asyncio
async def test_ingest_invalid_event_routes_to_dlq() -> None:
    malformed = {"raw_user_id": "alu_1", "action": ""}
    async with _build_client() as (client, producer):
        resp = await client.post("/api/v1/events", json=malformed)

    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "dlq"
    assert "dlq_id" in body

    assert len(producer.messages) == 1
    msg = producer.messages[0]
    assert msg.topic == Topics.DLQ_EVENTS
    assert msg.value["raw_payload"] == malformed


@pytest.mark.asyncio
async def test_ingest_batch_handles_valid_and_invalid_items() -> None:
    batch = [_sample_valid_event("alu_1"), {"bad": "event"}, _sample_valid_event("alu_2")]
    async with _build_client() as (client, producer):
        resp = await client.post("/api/v1/events/batch", json=batch)

    assert resp.status_code == 202
    body = resp.json()
    assert body["total"] == 3
    assert body["accepted"] == 2
    assert body["dlq"] == 1
    assert len(producer.messages) == 3
    topics = [m.topic for m in producer.messages]
    assert topics == [Topics.CANONICAL_EVENTS, Topics.DLQ_EVENTS, Topics.CANONICAL_EVENTS]


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_counters() -> None:
    async with _build_client() as (client, _):
        await client.post("/api/v1/events", json=_sample_valid_event())
        resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "dsm_gateway_events_total" in resp.text


@pytest.mark.asyncio
async def test_publish_run_eof_pseudonymizes_and_deduplicates_users() -> None:
    async with _build_client() as (client, producer):
        resp = await client.post(
            "/api/v1/runs/run_eof_01/eof",
            json={"raw_user_ids": ["alu_2", "alu_1", "alu_2", "   "], "course_id": "course_105"},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body == {"status": "eof_published", "run_id": "run_eof_01", "students_signaled": 2}
    assert len(producer.messages) == 2
    for msg in producer.messages:
        assert msg.topic == Topics.CANONICAL_EVENTS
        assert msg.value["event_type"] == "run_eof"
        assert msg.value["run_id"] == "run_eof_01"
        assert msg.value["course_id"] == "course_105"
        assert msg.key == msg.value["u"]
        assert msg.value["u"].startswith("usr_")
