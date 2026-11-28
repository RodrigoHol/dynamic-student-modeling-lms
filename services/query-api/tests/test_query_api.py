from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from dsm_common.schemas import (
    ClusteringResultMeta,
    ClusterSnapshotDocument,
    DfgEdge,
    DfgGraphDocument,
    DfgNode,
    ExplainabilityFeature,
    ExplainabilityMeta,
    ProfileLatenciesMs,
    StudentProfileDocument,
)
from dsm_common.storage import ExperimentMetricRecord
from dsm_query_api.config import QueryApiSettings
from dsm_query_api.main import create_app
from dsm_query_api.repositories import InMemoryQueryRepository
from dsm_query_api.schemas import CourseSummary, RunSummary, WsWindowUpdateEvent


def _seed_repository() -> InMemoryQueryRepository:
    repo = InMemoryQueryRepository()
    w1_start = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    w1_end = w1_start + timedelta(days=7)
    w2_start = w1_end
    w2_end = w2_start + timedelta(days=7)
    now = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)

    repo.courses["course_105"] = CourseSummary(
        course_id="course_105",
        external_code="INF-105",
        title="Inteligencia Artificial",
        start_date=w1_start,
        end_date=w2_end,
    )
    repo.runs["run_q_1"] = RunSummary(
        run_id="run_q_1",
        mode="stream",
        status="completed",
        source_dataset="synthetic.jsonl",
        speed_factor="max",
        events_processed=120,
        started_at=now - timedelta(minutes=2),
        finished_at=now,
        clustering_algorithm="denstream",
        active_granularities=["daily", "weekly", "monthly", "course"],
        course_ids=["course_105"],
    )

    def _prof(
        u: str,
        wid: str,
        ws: datetime,
        we: datetime,
        cid: int,
        prev_cid: int | None,
        trans: bool,
    ) -> StudentProfileDocument:
        return StudentProfileDocument(
            _id=f"run_q_1:weekly:{wid}:{u}",
            run_id="run_q_1",
            course_id="course_105",
            student_id=u,
            granularity="weekly",
            window_id=wid,
            window_start=ws,
            window_end=we,
            features_version="v0.1-provisional",
            features={"total_events": 18.0, "regularity_index": 0.8},
            clustering=ClusteringResultMeta(
                algorithm="denstream",
                cluster_id=cid,
                previous_cluster_id=prev_cid,
                transition_detected=trans,
                distance_to_centroid=0.25,
                is_outlier=cid < 0,
            ),
            explainability=ExplainabilityMeta(
                top_contributing_features=[
                    ExplainabilityFeature(feature="regularity_index", z_score=1.35),
                    ExplainabilityFeature(feature="total_events", z_score=0.72),
                ]
            ),
            latencies_ms=ProfileLatenciesMs(ingested_to_profile=18),
            updated_at=now,
        )

    repo.profiles.extend(
        [
            _prof("usr_1", "2024-W36", w1_start, w1_end, 0, None, False),
            _prof("usr_1", "2024-W37", w2_start, w2_end, 1, 0, True),
            _prof("usr_2", "2024-W36", w1_start, w1_end, 0, None, False),
            _prof("usr_2", "2024-W37", w2_start, w2_end, 0, 0, False),
        ]
    )
    repo.snapshots.append(
        ClusterSnapshotDocument(
            _id="run_q_1:weekly:2024-W37",
            run_id="run_q_1",
            course_id="course_105",
            granularity="weekly",
            window_id="2024-W37",
            window_start=w2_start,
            window_end=w2_end,
            algorithm="denstream",
            cluster_count=2,
            micro_cluster_count=2,
            centroids={"0": {"total_events": 15.0}, "1": {"total_events": 21.0}},
            cluster_weights={"0": 1.0, "1": 1.0},
            snapshot={},
            updated_at=now,
        )
    )
    repo.graphs[("run_q_1", "weekly", "2024-W37", "cluster", "1")] = DfgGraphDocument(
        run_id="run_q_1",
        course_id="course_105",
        granularity="weekly",
        window_id="2024-W37",
        window_start=w2_start,
        window_end=w2_end,
        scope="cluster",
        scope_id="1",
        trace_count=1,
        nodes=[
            DfgNode(code="START", label="Inicio", kind="boundary", category="boundary"),
            DfgNode(code="ACCESO_CURSO", label="Acceso al curso", kind="activity", category="hle"),
            DfgNode(code="ENVIO_TAREA", label="Envío de tarea", kind="activity", category="hle"),
            DfgNode(code="END", label="Fin", kind="boundary", category="boundary"),
        ],
        edges=[
            DfgEdge(
                source="START",
                target="ACCESO_CURSO",
                source_kind="boundary",
                target_kind="activity",
                freq=1,
                total_time_sec=0.0,
                mean_time_sec=0.0,
                trace_support_count=1,
                support=1.0,
            ),
            DfgEdge(
                source="ACCESO_CURSO",
                target="ENVIO_TAREA",
                source_kind="activity",
                target_kind="activity",
                freq=1,
                total_time_sec=45.0,
                mean_time_sec=45.0,
                trace_support_count=1,
                support=1.0,
            ),
            DfgEdge(
                source="ENVIO_TAREA",
                target="END",
                source_kind="activity",
                target_kind="boundary",
                freq=1,
                total_time_sec=0.0,
                mean_time_sec=0.0,
                trace_support_count=1,
                support=1.0,
            ),
        ],
        ingested_to_graph_ms=12,
        updated_at=now,
    )
    repo.metrics.append(
        ExperimentMetricRecord(
            metric_id=1,
            run_id="run_q_1",
            granularity="weekly",
            window_id="2024-W37",
            silhouette_score=0.64,
            ari_score=0.81,
            pm_fitness=0.95,
            pm_precision=0.88,
            p50_latency_ms=15.0,
            p95_latency_ms=22.0,
            p99_latency_ms=26.0,
            throughput_eps=510.0,
            computed_at=now,
        )
    )
    return repo


@asynccontextmanager
async def _build_client() -> AsyncIterator[tuple[httpx.AsyncClient, InMemoryQueryRepository]]:
    repo = _seed_repository()
    settings = QueryApiSettings(
        jwt_secret="test-jwt-secret-key-at-least-32-bytes-long",
        query_enable_ws_kafka_bridge=False,
    )
    app = create_app(repository=repo, settings=settings, enable_ws_bridge=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo


@pytest.mark.asyncio
async def test_auth_and_role_based_access_control() -> None:
    async with _build_client() as (client, _):
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/api/v1/courses")).status_code == 401

        bad_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "docente", "password": "wrong"},
        )
        assert bad_login.status_code == 401

        teacher_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "docente", "password": "docente123"},
        )
        assert teacher_login.status_code == 200
        teacher_token = teacher_login.json()["access_token"]
        teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

        me_resp = await client.get("/api/v1/auth/me", headers=teacher_headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["role"] == "teacher"

        # Teacher no puede acceder a ruta admin-only
        admin_only = await client.get("/api/v1/admin/overview", headers=teacher_headers)
        assert admin_only.status_code == 403

        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        ok_admin = await client.get("/api/v1/admin/overview", headers=admin_headers)
        assert ok_admin.status_code == 200
        assert ok_admin.json() == {"courses_count": 1, "runs_count": 1}


@pytest.mark.asyncio
async def test_query_endpoints_return_evolution_students_dfg_and_metrics() -> None:
    async with _build_client() as (client, _):
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "docente", "password": "docente123"},
        )
        headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        courses = await client.get("/api/v1/courses", headers=headers)
        assert courses.status_code == 200
        assert courses.json()[0]["course_id"] == "course_105"

        runs = await client.get("/api/v1/runs", headers=headers)
        assert runs.status_code == 200
        assert runs.json()[0]["run_id"] == "run_q_1"

        windows = await client.get(
            "/api/v1/runs/run_q_1/windows?granularity=weekly",
            headers=headers,
        )
        assert windows.status_code == 200
        assert len(windows.json()) == 2

        evo = await client.get(
            "/api/v1/runs/run_q_1/clusters/evolution?granularity=weekly",
            headers=headers,
        )
        assert evo.status_code == 200
        evo_body = evo.json()
        assert len(evo_body["windows"]) == 2
        assert len(evo_body["sankey_nodes"]) == 3
        links = {(lnk["source"], lnk["target"]): lnk["value"] for lnk in evo_body["sankey_links"]}
        assert links[("2024-W36::C0", "2024-W37::C1")] == 1
        assert links[("2024-W36::C0", "2024-W37::C0")] == 1

        c_students = await client.get(
            "/api/v1/runs/run_q_1/clusters/1/students?granularity=weekly&window_id=2024-W37",
            headers=headers,
        )
        assert c_students.status_code == 200
        assert c_students.json()[0]["student_id"] == "usr_1"
        assert c_students.json()[0]["transition_detected"] is True

        timeline = await client.get(
            "/api/v1/runs/run_q_1/students/usr_1?granularity=weekly",
            headers=headers,
        )
        assert timeline.status_code == 200
        assert len(timeline.json()["history"]) == 2
        assert timeline.json()["history"][1]["top_contributing_features"][0]["feature"] == (
            "regularity_index"
        )

        dfg = await client.get(
            "/api/v1/runs/run_q_1/dfg?granularity=weekly&window_id=2024-W37&scope=cluster&scope_id=1",
            headers=headers,
        )
        assert dfg.status_code == 200
        assert dfg.json()["trace_count"] == 1
        assert len(dfg.json()["edges"]) == 3

        metrics_resp = await client.get("/api/v1/runs/run_q_1/metrics", headers=headers)
        assert metrics_resp.status_code == 200
        assert metrics_resp.json()[0]["pm_fitness"] == pytest.approx(0.95)

        prom = await client.get("/metrics")
        assert prom.status_code == 200
        assert "dsm_query_api_requests_total" in prom.text


def test_websocket_broadcasts_window_update() -> None:
    repo = _seed_repository()
    settings = QueryApiSettings(
        jwt_secret="test-jwt-secret-key-at-least-32-bytes-long",
        query_enable_ws_kafka_bridge=False,
    )
    app = create_app(repository=repo, settings=settings, enable_ws_bridge=False)
    with TestClient(app) as client, client.websocket_connect("/ws/runs/run_q_1") as ws:
        event = WsWindowUpdateEvent(
            run_id="run_q_1",
            course_id="course_105",
            granularity="weekly",
            window_id="2024-W38",
            student_id="usr_1",
            cluster_id=1,
            transition_detected=False,
            emitted_at=datetime(2026, 11, 28, 10, 5, tzinfo=UTC),
        )
        import asyncio

        sent = asyncio.run(app.state.ws_manager.broadcast_update(event))
        assert sent == 1
        received = ws.receive_json()
        assert received["type"] == "window_updated"
        assert received["window_id"] == "2024-W38"
