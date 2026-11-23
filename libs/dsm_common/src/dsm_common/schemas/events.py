"""Esquemas Pydantic del flujo canónico y cola de errores (DLQ)."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ensure_utc(value: datetime) -> datetime:
    """Normaliza estampas temporales a UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ResourceInfo(BaseModel):
    """Recurso pedagógico o entidad instruccional de origen."""

    resource_id: str = Field(..., min_length=1)
    resource_type: str = Field(..., min_length=1)
    name: str | None = None


class EventMetadata(BaseModel):
    """Metadatos contextuales enriquecidos del evento (M)."""

    model_config = ConfigDict(extra="allow")

    course_id: str = Field(..., min_length=1)
    source_format: str = Field(default="unknown", min_length=1)
    component: str | None = None
    raw_eventname: str | None = None
    hle: str | None = None
    session_hash: str | None = None


class RawEventInput(BaseModel):
    """Contrato de entrada recibido por C2 Ingestion Gateway."""

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
        return _ensure_utc(value)


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
        return _ensure_utc(value)


class DlqEvent(BaseModel):
    """Evento derivado a la Dead Letter Queue cuando falla validación o normalización."""

    dlq_id: str = Field(..., min_length=1)
    received_at: datetime
    error_reason: str = Field(..., min_length=1)
    raw_payload: Any

    @field_validator("received_at")
    @classmethod
    def _normalize_received_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value)
