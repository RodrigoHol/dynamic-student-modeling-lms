from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from dsm_common.time import ensure_utc


class TraceEventItem(BaseModel):
    event_id: str = Field(..., min_length=1)
    hle: str = Field(..., min_length=1)
    t: datetime
    a: str = Field(..., min_length=1)
    resource_id: str = Field(..., min_length=1)
    resource_type: str = Field(..., min_length=1)
    session_hash: str | None = None

    @field_validator("t")
    @classmethod
    def _normalize_t(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class FeatureVectorMessage(BaseModel):
    run_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    u: str = Field(..., min_length=1)
    granularity: str = Field(..., min_length=1)
    window_id: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    features_version: str = Field(..., min_length=1)
    hle_version: str = Field(..., min_length=1)
    features: dict[str, float]
    event_count: int = Field(ge=0)
    last_event_ingested_at: datetime
    emitted_at: datetime

    @field_validator("window_start", "window_end", "last_event_ingested_at", "emitted_at")
    @classmethod
    def _normalize_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class TraceMessage(BaseModel):
    run_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    u: str = Field(..., min_length=1)
    granularity: str = Field(..., min_length=1)
    window_id: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    hle_version: str = Field(..., min_length=1)
    trace: list[TraceEventItem]
    event_count: int = Field(ge=0)
    last_event_ingested_at: datetime
    emitted_at: datetime

    @field_validator("window_start", "window_end", "last_event_ingested_at", "emitted_at")
    @classmethod
    def _normalize_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)
