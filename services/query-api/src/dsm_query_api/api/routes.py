from __future__ import annotations

from time import perf_counter
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from dsm_common.observability.metrics import render_metrics
from dsm_common.schemas import GraphScope
from dsm_common.storage import ExperimentMetricRecord
from dsm_query_api.auth import create_access_token, get_current_user, require_roles, verify_password
from dsm_query_api.config import QueryApiSettings
from dsm_query_api.metrics import QUERY_LATENCY_SECONDS, QUERY_REQUESTS_TOTAL
from dsm_query_api.repositories import QueryRepository
from dsm_query_api.schemas import (
    ClusterEvolutionResponse,
    ClusterStudentItem,
    CourseSummary,
    DfgGraphResponse,
    LoginRequest,
    RunSummary,
    StudentListItem,
    StudentTimelineResponse,
    TokenResponse,
    UserPublic,
    WindowSummary,
)
from dsm_query_api.websocket import ConnectionManager

router = APIRouter()

TeacherOrAdminUser = Annotated[UserPublic, Depends(require_roles("teacher", "admin"))]
AdminOnlyUser = Annotated[UserPublic, Depends(require_roles("admin"))]


def _repo(request: Request) -> QueryRepository:
    return request.app.state.repository


def _settings(request: Request) -> QueryApiSettings:
    return request.app.state.settings


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "query-api"}


@router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@router.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    repo = _repo(request)
    cfg = _settings(request)
    user = await repo.get_user_by_username(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        QUERY_REQUESTS_TOTAL.labels(endpoint="login", status="401").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )
    public_user = UserPublic(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        assigned_courses=user.assigned_courses,
    )
    token, ttl = create_access_token(public_user, cfg)
    QUERY_REQUESTS_TOTAL.labels(endpoint="login", status="200").inc()
    return TokenResponse(
        access_token=token,
        expires_in_seconds=ttl,
        user=public_user,
    )


@router.get("/api/v1/auth/me", response_model=UserPublic)
async def me(user: Annotated[UserPublic, Depends(get_current_user)]) -> UserPublic:
    return user


@router.get("/api/v1/courses", response_model=list[CourseSummary])
async def list_courses(
    request: Request,
    _user: TeacherOrAdminUser,
) -> list[CourseSummary]:
    started = perf_counter()
    try:
        items = await _repo(request).list_courses()
        QUERY_REQUESTS_TOTAL.labels(endpoint="courses", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="courses").observe(perf_counter() - started)


@router.get("/api/v1/runs", response_model=list[RunSummary])
async def list_runs(
    request: Request,
    _user: TeacherOrAdminUser,
    course_id: Annotated[str | None, Query()] = None,
) -> list[RunSummary]:
    started = perf_counter()
    try:
        items = await _repo(request).list_runs(course_id=course_id)
        QUERY_REQUESTS_TOTAL.labels(endpoint="runs", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="runs").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/windows", response_model=list[WindowSummary])
async def list_windows(
    run_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    granularity: Annotated[str | None, Query()] = None,
    course_id: Annotated[str | None, Query()] = None,
) -> list[WindowSummary]:
    started = perf_counter()
    try:
        items = await _repo(request).list_windows(
            run_id=run_id,
            granularity=granularity,
            course_id=course_id,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="windows", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="windows").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/clusters/evolution", response_model=ClusterEvolutionResponse)
async def get_cluster_evolution(
    run_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    granularity: Annotated[str, Query()] = "weekly",
    course_id: Annotated[str | None, Query()] = None,
) -> ClusterEvolutionResponse:
    started = perf_counter()
    try:
        res = await _repo(request).get_cluster_evolution(
            run_id=run_id,
            granularity=granularity,
            course_id=course_id,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="cluster_evolution", status="200").inc()
        return res
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="cluster_evolution").observe(perf_counter() - started)


@router.get(
    "/api/v1/runs/{run_id}/clusters/{cluster_id}/students",
    response_model=list[ClusterStudentItem],
)
async def list_cluster_students(
    run_id: str,
    cluster_id: int,
    request: Request,
    _user: TeacherOrAdminUser,
    window_id: Annotated[str, Query()],
    granularity: Annotated[str, Query()] = "weekly",
    course_id: Annotated[str | None, Query()] = None,
) -> list[ClusterStudentItem]:
    started = perf_counter()
    try:
        items = await _repo(request).list_cluster_students(
            run_id=run_id,
            granularity=granularity,
            window_id=window_id,
            cluster_id=cluster_id,
            course_id=course_id,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="cluster_students", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="cluster_students").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/students", response_model=list[StudentListItem])
async def list_students(
    run_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    granularity: Annotated[str, Query()] = "weekly",
    course_id: Annotated[str | None, Query()] = None,
) -> list[StudentListItem]:
    started = perf_counter()
    try:
        items = await _repo(request).list_students(
            run_id=run_id,
            granularity=granularity,
            course_id=course_id,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="students", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="students").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/students/{student_id}", response_model=StudentTimelineResponse)
async def get_student_timeline(
    run_id: str,
    student_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    granularity: Annotated[str, Query()] = "weekly",
) -> StudentTimelineResponse:
    started = perf_counter()
    try:
        timeline = await _repo(request).get_student_timeline(
            run_id=run_id,
            student_id=student_id,
            granularity=granularity,
        )
        if not timeline.history:
            QUERY_REQUESTS_TOTAL.labels(endpoint="student_timeline", status="404").inc()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existen perfiles para estudiante '{student_id}' en '{run_id}'.",
            )
        QUERY_REQUESTS_TOTAL.labels(endpoint="student_timeline", status="200").inc()
        return timeline
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="student_timeline").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/dfg", response_model=DfgGraphResponse)
async def get_dfg(
    run_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    window_id: Annotated[str, Query()],
    scope_id: Annotated[str, Query()],
    granularity: Annotated[str, Query()] = "weekly",
    scope: Annotated[GraphScope, Query()] = "cluster",
) -> DfgGraphResponse:
    started = perf_counter()
    try:
        graph = await _repo(request).get_dfg(
            run_id=run_id,
            granularity=granularity,
            window_id=window_id,
            scope=scope,
            scope_id=scope_id,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="dfg", status="200").inc()
        return graph
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="dfg").observe(perf_counter() - started)


@router.get("/api/v1/runs/{run_id}/metrics", response_model=list[ExperimentMetricRecord])
async def list_run_metrics(
    run_id: str,
    request: Request,
    _user: TeacherOrAdminUser,
    granularity: Annotated[str | None, Query()] = None,
) -> list[ExperimentMetricRecord]:
    started = perf_counter()
    try:
        items = await _repo(request).list_experiment_metrics(
            run_id=run_id,
            granularity=granularity,
        )
        QUERY_REQUESTS_TOTAL.labels(endpoint="experiment_metrics", status="200").inc()
        return items
    finally:
        QUERY_LATENCY_SECONDS.labels(endpoint="experiment_metrics").observe(
            perf_counter() - started
        )


@router.get("/api/v1/admin/overview")
async def admin_overview(
    request: Request,
    _user: AdminOnlyUser,
) -> dict[str, int]:
    courses = await _repo(request).list_courses()
    runs = await _repo(request).list_runs()
    return {"courses_count": len(courses), "runs_count": len(runs)}


async def _ws_channel_loop(websocket: WebSocket, channel: str) -> None:
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel)


@router.websocket("/ws/runs/{run_id}")
async def ws_run_updates(websocket: WebSocket, run_id: str) -> None:
    await _ws_channel_loop(websocket, run_id)


@router.websocket("/ws/updates")
async def ws_all_updates(websocket: WebSocket) -> None:
    await _ws_channel_loop(websocket, "*")
