from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ExplainabilityFeature(BaseModel):
    feature: str = Field(..., min_length=1)
    z_score: float


class ExplainabilityMeta(BaseModel):
    top_contributing_features: list[ExplainabilityFeature] = Field(default_factory=list)


class ClusteringResultMeta(BaseModel):
    algorithm: str = Field(..., min_length=1)
    cluster_id: int
    previous_cluster_id: int | None = None
    transition_detected: bool = False
    distance_to_centroid: float | None = None
    is_outlier: bool = False


class ProfileLatenciesMs(BaseModel):
    ingested_to_profile: int = Field(ge=0)


class StudentProfileDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id", min_length=1)
    run_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)
    granularity: str = Field(..., min_length=1)
    window_id: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    features_version: str = Field(..., min_length=1)
    features: dict[str, float]
    clustering: ClusteringResultMeta
    explainability: ExplainabilityMeta
    latencies_ms: ProfileLatenciesMs
    updated_at: datetime

    @field_validator("window_start", "window_end", "updated_at")
    @classmethod
    def _normalize_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    def to_mongo_doc(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="python")


class ClusterSnapshotDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id", min_length=1)
    run_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    granularity: str = Field(..., min_length=1)
    window_id: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    algorithm: str = Field(..., min_length=1)
    cluster_count: int = Field(ge=0)
    micro_cluster_count: int = Field(ge=0)
    centroids: dict[str, dict[str, float]] = Field(default_factory=dict)
    cluster_weights: dict[str, float] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime

    @field_validator("window_start", "window_end", "updated_at")
    @classmethod
    def _normalize_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    def to_mongo_doc(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="python")


class ClusterAssignmentMessage(BaseModel):
    run_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    u: str = Field(..., min_length=1)
    granularity: str = Field(..., min_length=1)
    window_id: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    algorithm: str = Field(..., min_length=1)
    cluster_id: int
    previous_cluster_id: int | None = None
    transition_detected: bool = False
    distance_to_centroid: float | None = None
    is_outlier: bool = False
    last_event_ingested_at: datetime
    emitted_at: datetime

    @field_validator("window_start", "window_end", "last_event_ingested_at", "emitted_at")
    @classmethod
    def _normalize_datetimes(cls, value: datetime) -> datetime:
        return ensure_utc(value)
