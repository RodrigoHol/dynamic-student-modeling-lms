from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from dsm_common.config import AppSettings
from dsm_common.messaging import EventProducer, PublishedMessage, Topics
from dsm_common.observability import render_metrics
from dsm_common.privacy import pseudonymize_user_id
from dsm_common.schemas import CanonicalEvent, DlqEvent, RunEofEvent, RunEofRequest
from dsm_common.time import utc_now
from dsm_gateway.metrics import EVENTS_RECEIVED_TOTAL, INGESTION_LATENCY_SECONDS
from dsm_gateway.normalizer import normalize_or_dlq

router = APIRouter()


def _to_published_message(outcome: CanonicalEvent | DlqEvent) -> PublishedMessage:
    if isinstance(outcome, CanonicalEvent):
        return PublishedMessage(
            topic=Topics.CANONICAL_EVENTS,
            key=outcome.u,
            value=outcome.model_dump(mode="json"),
        )
    return PublishedMessage(
        topic=Topics.DLQ_EVENTS,
        key=outcome.dlq_id,
        value=outcome.model_dump(mode="json"),
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ingestion-gateway"}


@router.get("/metrics")
async def metrics() -> Response:
    data, content_type = render_metrics()
    return Response(content=data, media_type=content_type)


@router.post("/api/v1/events", status_code=202)
async def ingest_event(request: Request, payload: Annotated[Any, Body()]) -> JSONResponse:
    producer: EventProducer = request.app.state.producer
    settings: AppSettings = request.app.state.settings

    started = perf_counter()
    outcome = normalize_or_dlq(payload, settings)
    message = _to_published_message(outcome)
    await producer.publish(message.topic, key=message.key, value=message.value)
    INGESTION_LATENCY_SECONDS.observe(perf_counter() - started)

    if isinstance(outcome, CanonicalEvent):
        EVENTS_RECEIVED_TOTAL.labels(status="accepted").inc()
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "event_id": outcome.event_id,
                "run_id": outcome.run_id,
                "u": outcome.u,
                "ingested_at": outcome.ingested_at.isoformat(),
            },
        )

    EVENTS_RECEIVED_TOTAL.labels(status="dlq").inc()
    return JSONResponse(
        status_code=422,
        content={
            "status": "dlq",
            "dlq_id": outcome.dlq_id,
            "error_reason": outcome.error_reason,
        },
    )


@router.post("/api/v1/events/batch", status_code=202)
async def ingest_events_batch(
    request: Request,
    payload: Annotated[Any, Body()],
) -> JSONResponse:
    producer: EventProducer = request.app.state.producer
    settings: AppSettings = request.app.state.settings

    items: Any = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        outcome = normalize_or_dlq(
            payload, settings
        ) if not isinstance(payload, dict) else None
        if isinstance(outcome, DlqEvent):
            dlq = outcome
        else:
            dlq = DlqEvent(
                dlq_id=str(uuid4()),
                received_at=utc_now(),
                error_reason=(
                    "El lote debe ser una lista JSON o un objeto con la clave 'events'."
                ),
                raw_payload=payload,
            )
        await producer.publish(
            Topics.DLQ_EVENTS,
            key=dlq.dlq_id,
            value=dlq.model_dump(mode="json"),
        )
        EVENTS_RECEIVED_TOTAL.labels(status="dlq").inc()
        return JSONResponse(
            status_code=422,
            content={
                "status": "dlq",
                "dlq_id": dlq.dlq_id,
                "error_reason": dlq.error_reason,
            },
        )

    started = perf_counter()
    outcomes = [normalize_or_dlq(item, settings) for item in items]
    messages = [_to_published_message(outcome) for outcome in outcomes]
    await producer.publish_batch(messages)
    INGESTION_LATENCY_SECONDS.observe(perf_counter() - started)

    dlq_ids = [out.dlq_id for out in outcomes if isinstance(out, DlqEvent)]
    accepted = len(outcomes) - len(dlq_ids)
    if accepted:
        EVENTS_RECEIVED_TOTAL.labels(status="accepted").inc(accepted)
    if dlq_ids:
        EVENTS_RECEIVED_TOTAL.labels(status="dlq").inc(len(dlq_ids))

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


@router.post("/api/v1/runs/{run_id}/eof", status_code=202)
async def publish_run_eof(
    run_id: str,
    request: Request,
    payload: RunEofRequest,
) -> JSONResponse:
    """Emite marcadores en-banda `RunEofEvent` particionados por `u` para cada estudiante."""
    clean_run_id = run_id.strip()
    if not clean_run_id:
        raise HTTPException(status_code=422, detail="El parámetro run_id no puede estar vacío.")

    producer: EventProducer = request.app.state.producer
    settings: AppSettings = request.app.state.settings

    unique_raw_ids = sorted(
        {uid.strip() for uid in payload.raw_user_ids if uid and uid.strip()}
    )
    now = utc_now()
    messages: list[PublishedMessage] = []

    for raw_uid in unique_raw_ids:
        pseudo_u = pseudonymize_user_id(raw_uid, settings.pseudonym_salt)
        eof_event = RunEofEvent(
            event_id=str(uuid4()),
            run_id=clean_run_id,
            u=pseudo_u,
            course_id=payload.course_id,
            emitted_at=now,
        )
        messages.append(
            PublishedMessage(
                topic=Topics.CANONICAL_EVENTS,
                key=pseudo_u,
                value=eof_event.model_dump(mode="json"),
            )
        )

    await producer.publish_batch(messages)
    return JSONResponse(
        status_code=202,
        content={
            "status": "eof_published",
            "run_id": clean_run_id,
            "students_signaled": len(unique_raw_ids),
        },
    )
