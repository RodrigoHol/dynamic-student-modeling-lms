from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from time import perf_counter
from typing import Any

import httpx

from dsm_common.schemas import RawEventInput
from dsm_common.storage import RunConfigSnapshot, RunRepository


@dataclass(frozen=True, slots=True)
class SpeedConfig:
    raw: str
    factor: float | None
    is_max: bool


def parse_speed_factor(value: str) -> SpeedConfig:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("El factor de velocidad no puede estar vacío.")
    if cleaned == "max":
        return SpeedConfig(raw="max", factor=None, is_max=True)

    numeric_str = cleaned[:-1] if cleaned.endswith("x") else cleaned
    try:
        factor = float(numeric_str)
    except ValueError as exc:
        raise ValueError(
            f"Velocidad inválida '{value}'. Usa 'max' o un factor positivo "
            "como '1x', '10x', '100x'."
        ) from exc

    if factor <= 0:
        raise ValueError(f"El factor de velocidad debe ser mayor que cero: '{value}'.")

    return SpeedConfig(raw=f"{factor:g}x", factor=factor, is_max=False)


@dataclass(slots=True)
class ReplayStats:
    run_id: str
    source_dataset: str
    format_name: str
    speed_factor: str
    total_events: int
    accepted_events: int
    dlq_events: int
    elapsed_seconds: float
    throughput_eps: float


def _chunked(iterable: Iterable[RawEventInput], size: int) -> Iterable[list[RawEventInput]]:
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


def _compute_delay(
    event_ts: datetime,
    prev_ts: datetime | None,
    speed: SpeedConfig,
    max_delay_seconds: float | None,
) -> float:
    if speed.is_max or prev_ts is None or speed.factor is None:
        return 0.0
    delay = max(0.0, (event_ts - prev_ts).total_seconds() / speed.factor)
    if max_delay_seconds is not None:
        return min(delay, max_delay_seconds)
    return delay


class ReplayDispatcher:
    def __init__(
        self,
        gateway_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        run_repository: RunRepository | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
        batch_size: int = 100,
        max_retries: int = 3,
        request_timeout: float = 60.0,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size debe ser >= 1.")
        if max_retries < 1:
            raise ValueError("max_retries debe ser >= 1.")
        self._gateway_url = gateway_url.rstrip("/")
        self._external_client = client
        self._run_repository = run_repository
        self._sleep_fn = sleep_fn
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._request_timeout = request_timeout

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: Any,
    ) -> httpx.Response:
        url = f"{self._gateway_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = await client.post(url, json=payload)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt + 1 < self._max_retries:
                    await self._sleep_fn(0.25 * (2**attempt))
                    continue
                raise

            if response.status_code >= 500 and attempt + 1 < self._max_retries:
                await self._sleep_fn(0.25 * (2**attempt))
                continue
            return response

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Reintentos agotados enviando POST a {url}.")

    async def _replay_batches(
        self,
        client: httpx.AsyncClient,
        events: Iterable[RawEventInput],
        seen_raw_users: set[str],
    ) -> tuple[int, int, int, str | None]:
        total = 0
        accepted = 0
        dlq = 0
        last_course_id: str | None = None

        for batch in _chunked(events, self._batch_size):
            payload = {"events": [item.model_dump(mode="json") for item in batch]}
            response = await self._post_with_retry(client, "/api/v1/events/batch", payload)
            if response.status_code != 202:
                raise RuntimeError(
                    f"Error inesperado del Gateway ({response.status_code}): {response.text}"
                )
            body = response.json()
            batch_accepted = int(body.get("accepted", 0))
            total += len(batch)
            accepted += batch_accepted
            dlq += int(body.get("dlq", 0))
            if batch_accepted > 0:
                seen_raw_users.update(item.raw_user_id for item in batch)
                last_course_id = batch[-1].metadata.course_id

        return total, accepted, dlq, last_course_id

    async def _replay_timed(
        self,
        client: httpx.AsyncClient,
        events: Iterable[RawEventInput],
        speed: SpeedConfig,
        max_delay_seconds: float | None,
        seen_raw_users: set[str],
    ) -> tuple[int, int, int, str | None]:
        total = 0
        accepted = 0
        dlq = 0
        last_course_id: str | None = None
        prev_ts: datetime | None = None

        for event in events:
            delay = _compute_delay(event.timestamp, prev_ts, speed, max_delay_seconds)
            if delay > 0.0:
                await self._sleep_fn(delay)
            prev_ts = event.timestamp

            response = await self._post_with_retry(
                client,
                "/api/v1/events",
                event.model_dump(mode="json"),
            )
            total += 1
            if response.status_code == 202:
                accepted += 1
                seen_raw_users.add(event.raw_user_id)
                last_course_id = event.metadata.course_id
            elif response.status_code == 422:
                dlq += 1
            else:
                raise RuntimeError(
                    f"Error inesperado del Gateway ({response.status_code}): {response.text}"
                )

        return total, accepted, dlq, last_course_id

    async def _emit_eof(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        raw_user_ids: set[str],
        course_id: str | None,
    ) -> None:
        response = await self._post_with_retry(
            client,
            f"/api/v1/runs/{run_id}/eof",
            {"raw_user_ids": sorted(raw_user_ids), "course_id": course_id},
        )
        if response.status_code != 202:
            raise RuntimeError(
                f"Error inesperado del Gateway al emitir EOF ({response.status_code}): "
                f"{response.text}"
            )

    async def replay(
        self,
        events: Iterable[RawEventInput],
        *,
        run_id: str,
        source_dataset: str,
        format_name: str,
        speed: SpeedConfig,
        config_snapshot: RunConfigSnapshot | None = None,
        max_delay_seconds: float | None = None,
        limit: int | None = None,
        emit_eof: bool = False,
    ) -> ReplayStats:
        if limit is not None and limit < 0:
            raise ValueError("limit debe ser >= 0.")

        if self._run_repository is not None:
            await self._run_repository.start_run(
                run_id=run_id,
                mode="stream",
                source_dataset=source_dataset,
                speed_factor=speed.raw,
                config_snapshot=config_snapshot,
            )

        accepted_events = 0
        seen_raw_users: set[str] = set()
        started_perf = perf_counter()

        owns_client = self._external_client is None
        client = (
            self._external_client
            if self._external_client is not None
            else httpx.AsyncClient(timeout=self._request_timeout)
        )

        stream = islice(events, limit) if limit is not None else events
        tagged_events = (ev.model_copy(update={"run_id": run_id}) for ev in stream)

        try:
            if speed.is_max and self._batch_size > 1:
                total_events, accepted_events, dlq_events, last_course_id = (
                    await self._replay_batches(client, tagged_events, seen_raw_users)
                )
            else:
                total_events, accepted_events, dlq_events, last_course_id = (
                    await self._replay_timed(
                        client, tagged_events, speed, max_delay_seconds, seen_raw_users
                    )
                )

            if emit_eof and seen_raw_users:
                await self._emit_eof(client, run_id, seen_raw_users, last_course_id)

            elapsed = perf_counter() - started_perf
            if self._run_repository is not None:
                await self._run_repository.complete_run(run_id, events_processed=accepted_events)

            return ReplayStats(
                run_id=run_id,
                source_dataset=source_dataset,
                format_name=format_name,
                speed_factor=speed.raw,
                total_events=total_events,
                accepted_events=accepted_events,
                dlq_events=dlq_events,
                elapsed_seconds=elapsed,
                throughput_eps=(total_events / elapsed if elapsed > 0 else 0.0),
            )
        except Exception:
            if self._run_repository is not None:
                await self._run_repository.fail_run(run_id, events_processed=accepted_events)
            raise
        finally:
            if owns_client:
                await client.aclose()
