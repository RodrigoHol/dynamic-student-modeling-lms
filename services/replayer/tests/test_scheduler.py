from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from dsm_common.config import AppSettings
from dsm_common.messaging import InMemoryEventProducer, Topics
from dsm_common.schemas import EventMetadata, RawEventInput, ResourceInfo
from dsm_common.storage import InMemoryRunRepository
from dsm_gateway.main import create_app
from dsm_replayer.generator import SyntheticCourseConfig, generate_synthetic_events
from dsm_replayer.scheduler import ReplayDispatcher, parse_speed_factor


def test_parse_speed_factor() -> None:
    assert parse_speed_factor("max").is_max is True
    assert parse_speed_factor("MAX").is_max is True
    s1 = parse_speed_factor("1x")
    assert s1.is_max is False and s1.factor == 1.0
    s10 = parse_speed_factor("10x")
    assert s10.factor == 10.0 and s10.raw == "10x"
    s_half = parse_speed_factor("0.5")
    assert s_half.factor == 0.5

    for invalid in ["", "0x", "-5x", "fast"]:
        with pytest.raises(ValueError):
            parse_speed_factor(invalid)


@asynccontextmanager
async def _gateway_client():
    producer = InMemoryEventProducer()
    settings = AppSettings(pseudonym_salt="phase2-test-salt", default_run_id="run_default")
    app = create_app(producer=producer, settings=settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, producer


@pytest.mark.asyncio
async def test_dispatcher_max_mode_preserves_order_and_zero_loss_with_gateway() -> None:
    events = generate_synthetic_events(
        SyntheticCourseConfig(num_students=10, num_weeks=2, seed=99, target_events=250)
    )
    run_repo = InMemoryRunRepository()

    async with _gateway_client() as (client, producer):
        dispatcher = ReplayDispatcher(
            "http://test",
            client=client,
            run_repository=run_repo,
            batch_size=40,
        )
        stats = await dispatcher.replay(
            events,
            run_id="run_e2e_mem_001",
            source_dataset="synthetic_mem",
            format_name="synthetic_jsonl",
            speed=parse_speed_factor("max"),
        )

    assert stats.total_events == 250
    assert stats.accepted_events == 250
    assert stats.dlq_events == 0

    canonical_msgs = [m for m in producer.messages if m.topic == Topics.CANONICAL_EVENTS]
    assert len(canonical_msgs) == 250

    per_student_ts: dict[str, list[datetime]] = defaultdict(list)
    for msg in canonical_msgs:
        assert msg.value["run_id"] == "run_e2e_mem_001"
        assert msg.key == msg.value["u"]
        per_student_ts[msg.value["u"]].append(datetime.fromisoformat(msg.value["t"]))

    for ts_list in per_student_ts.values():
        assert ts_list == sorted(ts_list)

    run_record = await run_repo.get_run("run_e2e_mem_001")
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.events_processed == 250


@pytest.mark.asyncio
async def test_dispatcher_timed_mode_calculates_scaled_delays() -> None:
    base = datetime(2024, 9, 2, 10, 0, 0, tzinfo=UTC)
    events = [
        RawEventInput(
            raw_user_id="alu_1",
            action="viewed",
            resource=ResourceInfo(resource_id="c1", resource_type="course"),
            timestamp=base + timedelta(seconds=offset),
            metadata=EventMetadata(course_id="course_105"),
        )
        for offset in (0, 100, 1000)
    ]
    recorded_sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded_sleeps.append(seconds)

    async with _gateway_client() as (client, producer):
        dispatcher = ReplayDispatcher(
            "http://test",
            client=client,
            sleep_fn=fake_sleep,
        )
        stats = await dispatcher.replay(
            events,
            run_id="run_timed_01",
            source_dataset="mem",
            format_name="synthetic_jsonl",
            speed=parse_speed_factor("10x"),
            max_delay_seconds=5.0,
        )

    assert stats.accepted_events == 3
    assert len(producer.messages) == 3
    # 100s / 10 = 10s -> capped at 5.0s; 900s / 10 = 90s -> capped at 5.0s
    assert recorded_sleeps == [5.0, 5.0]


@pytest.mark.asyncio
async def test_dispatcher_marks_run_failed_on_gateway_error() -> None:
    events = generate_synthetic_events(
        SyntheticCourseConfig(num_students=2, num_weeks=1, seed=1, target_events=5)
    )
    run_repo = InMemoryRunRepository()

    def _failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    async def no_sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_failing_handler),
        base_url="http://test",
    ) as client:
        dispatcher = ReplayDispatcher(
            "http://test",
            client=client,
            run_repository=run_repo,
            sleep_fn=no_sleep,
            max_retries=2,
        )
        with pytest.raises(RuntimeError):
            await dispatcher.replay(
                events,
                run_id="run_fail_01",
                source_dataset="mem",
                format_name="synthetic_jsonl",
                speed=parse_speed_factor("max"),
            )

    record = await run_repo.get_run("run_fail_01")
    assert record is not None
    assert record.status == "failed"
