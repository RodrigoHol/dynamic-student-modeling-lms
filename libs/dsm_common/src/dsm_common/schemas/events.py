from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dsm_common.time import ensure_utc, utc_now


class Granularity(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    COURSE = "course"


class ResourceInfo(BaseModel):
    resource_id: str = Field(..., min_length=1)
    resource_type: str = Field(..., min_length=1)
    name: str | None = None


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    course_id: str = Field(..., min_length=1)
    source_format: str = Field(default="unknown", min_length=1)
    component: str | None = None
    raw_eventname: str | None = None
    hle: str | None = None
    session_hash: str | None = None


class RawEventInput(BaseModel):
    run_id: str | None = None
    raw_user_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    resource: ResourceInfo
    timestamp: datetime
    metadata: EventMetadata

    @field_validator("raw_user_id", "action")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("El campo no puede estar vacío.")
        return stripped

    @field_validator("timestamp")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class CanonicalEvent(BaseModel):
    """Evento canónico E = <u, a, r, t, M> almacenado en el log inmutable."""

    event_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    u: str = Field(..., min_length=1)
    a: str = Field(..., min_length=1)
    r: ResourceInfo
    t: datetime
    ingested_at: datetime
    M: EventMetadata

    @field_validator("t", "ingested_at")
    @classmethod
    def _normalize_dates(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class DlqEvent(BaseModel):
    dlq_id: str = Field(..., min_length=1)
    received_at: datetime
    error_reason: str = Field(..., min_length=1)
    raw_payload: Any

    @field_validator("received_at")
    @classmethod
    def _normalize_received_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


def make_dlq_event(
    raw_payload: Any,
    error_reason: str,
    *,
    received_at: datetime | None = None,
) -> DlqEvent:
    return DlqEvent(
        dlq_id=str(uuid4()),
        received_at=received_at or utc_now(),
        error_reason=error_reason,
        raw_payload=raw_payload,
    )


class RunEofRequest(BaseModel):
    raw_user_ids: list[str] = Field(default_factory=list)
    course_id: str | None = None


class RunEofEvent(BaseModel):
    """Marcador de control en-banda para cerrar ventanas pendientes por estudiante."""

    event_type: Literal["run_eof"] = "run_eof"
    event_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    u: str = Field(..., min_length=1)
    course_id: str | None = None
    emitted_at: datetime

    @field_validator("emitted_at")
    @classmethod
    def _normalize_emitted_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
