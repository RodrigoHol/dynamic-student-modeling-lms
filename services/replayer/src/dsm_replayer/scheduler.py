"""Despachador asíncrono de eventos con control de velocidad hacia C2 Gateway."""

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
    """Configuración parseada del factor de aceleración temporal."""

    raw: str
    factor: float | None
    is_max: bool


def parse_speed_factor(value: str) -> SpeedConfig:
    """Convierte cadenas como `'1x'`, `'10x'`, `'0.5x'` o `'max'` en `SpeedConfig`."""
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

    normalized_raw = f"{factor:g}x"
    return SpeedConfig(raw=normalized_raw, factor=factor, is_max=False)


@dataclass(slots=True)
class ReplayStats:
    """Resumen cuantitativo de una corrida ejecutada por C3 Replayer."""

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


class ReplayDispatcher:
    """Envía eventos en orden cronológico hacia C2 Gateway con control de velocidad."""

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

        assert last_exc is not None
        raise last_exc

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
        """Reproduce el flujo de eventos hacia C2 registrando el ciclo de vida de `run_id`."""
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
        dlq_events = 0
        total_events = 0
        seen_raw_users: set[str] = set()
        last_course_id: str | None = None
        started_perf = perf_counter()

        owns_client = self._external_client is None
        client = (
            self._external_client
            if self._external_client is not None
            else httpx.AsyncClient(timeout=self._request_timeout)
        )

        def _limited_events() -> Iterable[RawEventInput]:
            stream = islice(events, limit) if limit is not None else events
            for ev in stream:
                yield ev.model_copy(update={"run_id": run_id})

        try:
            if speed.is_max and self._batch_size > 1:
                for batch in _chunked(_limited_events(), self._batch_size):
                    payload = {"events": [item.model_dump(mode="json") for item in batch]}
                    response = await self._post_with_retry(client, "/api/v1/events/batch", payload)
                    if response.status_code != 202:
                        raise RuntimeError(
                            f"Error inesperado del Gateway ({response.status_code}): "
                            f"{response.text}"
                        )
                    body = response.json()
                    batch_accepted = int(body.get("accepted", 0))
                    total_events += len(batch)
                    accepted_events += batch_accepted
                    dlq_events += int(body.get("dlq", 0))
                    if batch_accepted > 0:
                        seen_raw_users.update(item.raw_user_id for item in batch)
                        last_course_id = batch[-1].metadata.course_id
            else:
                prev_ts: datetime | None = None
                for event in _limited_events():
                    if not speed.is_max and prev_ts is not None and speed.factor is not None:
                        delta = (event.timestamp - prev_ts).total_seconds()
                        delay = max(0.0, delta / speed.factor)
                        if max_delay_seconds is not None:
                            delay = min(delay, max_delay_seconds)
                        if delay > 0.0:
                            await self._sleep_fn(delay)
                    prev_ts = event.timestamp

                    response = await self._post_with_retry(
                        client,
                        "/api/v1/events",
                        event.model_dump(mode="json"),
                    )
                    total_events += 1
                    if response.status_code == 202:
                        accepted_events += 1
                        seen_raw_users.add(event.raw_user_id)
                        last_course_id = event.metadata.course_id
                    elif response.status_code == 422:
                        dlq_events += 1
                    else:
                        raise RuntimeError(
                            f"Error inesperado del Gateway ({response.status_code}): "
                            f"{response.text}"
                        )

            if emit_eof and seen_raw_users:
                eof_resp = await self._post_with_retry(
                    client,
                    f"/api/v1/runs/{run_id}/eof",
                    {"raw_user_ids": sorted(seen_raw_users), "course_id": last_course_id},
                )
                if eof_resp.status_code != 202:
                    raise RuntimeError(
                        f"Error inesperado del Gateway al emitir EOF ({eof_resp.status_code}): "
                        f"{eof_resp.text}"
                    )

            elapsed = perf_counter() - started_perf
            if self._run_repository is not None:
                await self._run_repository.complete_run(run_id, events_processed=accepted_events)

            throughput = total_events / elapsed if elapsed > 0 else 0.0
            return ReplayStats(
                run_id=run_id,
                source_dataset=source_dataset,
                format_name=format_name,
                speed_factor=speed.raw,
                total_events=total_events,
                accepted_events=accepted_events,
                dlq_events=dlq_events,
                elapsed_seconds=elapsed,
                throughput_eps=throughput,
            )
        except Exception:
            if self._run_repository is not None:
                await self._run_repository.fail_run(run_id, events_processed=accepted_events)
            raise
        finally:
            if owns_client:
                await client.aclose()
