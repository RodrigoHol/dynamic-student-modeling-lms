"""Rutas HTTP del Ingestion Gateway (C2)."""

from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from dsm_common.config import AppSettings
from dsm_common.messaging import EventProducer, Topics
from dsm_common.observability import (
    EVENTS_RECEIVED_TOTAL,
    INGESTION_LATENCY_SECONDS,
    render_metrics,
)
from dsm_common.schemas import CanonicalEvent, DlqEvent
from dsm_gateway.normalizer import normalize_or_dlq

router = APIRouter()


async def _ingest_single(
    payload: Any,
    producer: EventProducer,
    settings: AppSettings,
) -> tuple[CanonicalEvent | None, DlqEvent | None]:
    start = perf_counter()
    canonical, dlq = normalize_or_dlq(payload, settings)
    if canonical is not None:
        await producer.publish(
            Topics.CANONICAL_EVENTS,
            key=canonical.u,
            value=canonical.model_dump(mode="json"),
        )
        EVENTS_RECEIVED_TOTAL.labels(status="accepted").inc()
    else:
        assert dlq is not None
        await producer.publish(
            Topics.DLQ_EVENTS,
            key=dlq.dlq_id,
            value=dlq.model_dump(mode="json"),
        )
        EVENTS_RECEIVED_TOTAL.labels(status="dlq").inc()
    INGESTION_LATENCY_SECONDS.observe(perf_counter() - start)
    return canonical, dlq


@router.get("/health")
async def health() -> dict[str, str]:
    """Verifica disponibilidad del servicio."""
    return {"status": "ok", "service": "ingestion-gateway"}


@router.get("/metrics")
async def metrics() -> Response:
    """Expone métricas Prometheus del servicio."""
    data, content_type = render_metrics()
    return Response(content=data, media_type=content_type)


@router.post("/api/v1/events", status_code=202)
async def ingest_event(request: Request, payload: Annotated[Any, Body()]) -> JSONResponse:
    """Recibe un evento individual, lo normaliza y lo publica en Kafka."""
    producer: EventProducer = request.app.state.producer
    settings: AppSettings = request.app.state.settings
    canonical, dlq = await _ingest_single(payload, producer, settings)

    if canonical is not None:
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "event_id": canonical.event_id,
                "run_id": canonical.run_id,
                "u": canonical.u,
                "ingested_at": canonical.ingested_at.isoformat(),
            },
        )

    assert dlq is not None
    return JSONResponse(
        status_code=422,
        content={
            "status": "dlq",
            "dlq_id": dlq.dlq_id,
            "error_reason": dlq.error_reason,
        },
    )


@router.post("/api/v1/events/batch", status_code=202)
async def ingest_events_batch(
    request: Request,
    payload: Annotated[Any, Body()],
) -> JSONResponse:
    """Recibe un lote de eventos (p. ej. desde C3 Replayer) y enruta válidos o a DLQ."""
    producer: EventProducer = request.app.state.producer
    settings: AppSettings = request.app.state.settings

    items: Any = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        _, dlq = await _ingest_single(payload, producer, settings)
        assert dlq is not None
        return JSONResponse(
            status_code=422,
            content={
                "status": "dlq",
                "dlq_id": dlq.dlq_id,
                "error_reason": (
                    "El lote debe ser una lista JSON o un objeto con la clave 'events'."
                ),
            },
        )

    accepted = 0
    dlq_ids: list[str] = []
    for item in items:
        canonical, dlq = await _ingest_single(item, producer, settings)
        if canonical is not None:
            accepted += 1
        elif dlq is not None:
            dlq_ids.append(dlq.dlq_id)

    return JSONResponse(
        status_code=202,
        content={
            "status": "processed",
            "total": len(items),
            "accepted": accepted,
            "dlq": len(dlq_ids),
            "dlq_ids": dlq_ids,
        },
    )
