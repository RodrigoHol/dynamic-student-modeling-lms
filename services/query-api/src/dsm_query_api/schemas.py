from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from dsm_common.schemas import DfgEdge, DfgNode, ExplainabilityFeature, GraphScope


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserPublic(BaseModel):
    user_id: str
    username: str
    role: Literal["teacher", "admin"]
    assigned_courses: list[str] = Field(default_factory=list)


class UserRecord(UserPublic):
    password_hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserPublic


class CourseSummary(BaseModel):
    course_id: str
    external_code: str | None = None
    title: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class RunSummary(BaseModel):
    run_id: str
    mode: str
    status: str
    source_dataset: str
    speed_factor: str | None = None
    events_processed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    clustering_algorithm: str | None = None
    active_granularities: list[str] = Field(default_factory=list)
    course_ids: list[str] = Field(default_factory=list)


class WindowSummary(BaseModel):
    granularity: str
    window_id: str
    window_start: datetime
    window_end: datetime
    student_count: int
    transition_count: int
    cluster_count: int


class SankeyNode(BaseModel):
    id: str
    name: str
    window_id: str
    cluster_id: str


class SankeyLink(BaseModel):
    source: str
    target: str
    value: int


class WindowClusterDistribution(BaseModel):
    window_id: str
    window_start: datetime
    window_end: datetime
    counts: dict[str, int]
    total_students: int
    transition_count: int
    centroids: dict[str, dict[str, float]] = Field(default_factory=dict)


class ClusterEvolutionResponse(BaseModel):
    run_id: str
    granularity: str
    course_id: str | None = None
    windows: list[WindowClusterDistribution] = Field(default_factory=list)
    sankey_nodes: list[SankeyNode] = Field(default_factory=list)
    sankey_links: list[SankeyLink] = Field(default_factory=list)


class ClusterStudentItem(BaseModel):
    student_id: str
    cluster_id: int
    previous_cluster_id: int | None = None
    transition_detected: bool = False
    distance_to_centroid: float | None = None
    is_outlier: bool = False
    features: dict[str, float] = Field(default_factory=dict)
    top_contributing_features: list[ExplainabilityFeature] = Field(default_factory=list)


class StudentListItem(BaseModel):
    student_id: str
    latest_window_id: str
    latest_cluster_id: int
    transition_count: int
    total_windows: int


class StudentWindowEntry(BaseModel):
    window_id: str
    window_start: datetime
    window_end: datetime
    algorithm: str
    cluster_id: int
    previous_cluster_id: int | None = None
    transition_detected: bool = False
    distance_to_centroid: float | None = None
    is_outlier: bool = False
    features: dict[str, float] = Field(default_factory=dict)
    top_contributing_features: list[ExplainabilityFeature] = Field(default_factory=list)
    ingested_to_profile_ms: int = 0


class StudentTimelineResponse(BaseModel):
    run_id: str
    course_id: str | None = None
    granularity: str
    student_id: str
    history: list[StudentWindowEntry] = Field(default_factory=list)


class DfgGraphResponse(BaseModel):
    run_id: str
    course_id: str | None = None
    granularity: str
    window_id: str
    scope: GraphScope
    scope_id: str
    trace_count: int = 0
    nodes: list[DfgNode] = Field(default_factory=list)
    edges: list[DfgEdge] = Field(default_factory=list)


class WsWindowUpdateEvent(BaseModel):
    type: Literal["window_updated"] = "window_updated"
    run_id: str
    course_id: str
    granularity: str
    window_id: str
    student_id: str
    cluster_id: int
    transition_detected: bool = False
    emitted_at: datetime
