from __future__ import annotations

import asyncio
import itertools
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dsm_common.schemas import (
    ClusterSnapshotDocument,
    DfgEdge,
    DfgGraphDocument,
    DfgNode,
    ExplainabilityFeature,
    GraphScope,
    NodeKind,
    StudentProfileDocument,
)
from dsm_common.storage import ExperimentMetricRecord
from dsm_query_api.auth import build_demo_user_records
from dsm_query_api.schemas import (
    ClusterEvolutionResponse,
    ClusterStudentItem,
    CourseSummary,
    DfgGraphResponse,
    RunSummary,
    SankeyLink,
    SankeyNode,
    StudentListItem,
    StudentTimelineResponse,
    StudentWindowEntry,
    UserRecord,
    WindowClusterDistribution,
    WindowSummary,
)

if TYPE_CHECKING:
    import asyncpg
    from neo4j import AsyncDriver
    from pymongo import AsyncMongoClient

_HLE_LABELS: dict[str, str] = {
    "START": "Inicio",
    "END": "Fin",
    "ACCESO_CURSO": "Acceso al curso",
    "CONSULTA_RECURSO": "Consulta de recurso",
    "PARTICIPACION_FORO": "Participación en foro",
    "ENVIO_TAREA": "Envío de tarea",
    "INTENTO_CUESTIONARIO": "Intento de cuestionario",
    "REVISION_RETROALIMENTACION": "Revisión de retroalimentación",
    "OTRO": "Otra actividad",
}

_NEO4J_READ_DFG_CYPHER = """
MATCH (src)-[r:DFG {
    run_id: $run_id,
    granularity: $granularity,
    window_id: $window_id,
    scope: $scope,
    scope_id: $scope_id
}]->(dst)
RETURN
    CASE WHEN src:Boundary THEN src.name ELSE src.hle_code END AS source,
    CASE WHEN src:Boundary THEN 'boundary' ELSE 'activity' END AS source_kind,
    coalesce(src.label, CASE WHEN src:Boundary THEN src.name ELSE src.hle_code END) AS src_label,
    coalesce(src.category, CASE WHEN src:Boundary THEN 'boundary' ELSE 'hle' END) AS src_category,
    CASE WHEN dst:Boundary THEN dst.name ELSE dst.hle_code END AS target,
    CASE WHEN dst:Boundary THEN 'boundary' ELSE 'activity' END AS target_kind,
    coalesce(dst.label, CASE WHEN dst:Boundary THEN dst.name ELSE dst.hle_code END) AS dst_label,
    coalesce(dst.category, CASE WHEN dst:Boundary THEN 'boundary' ELSE 'hle' END) AS dst_category,
    r.freq AS freq,
    r.total_time_sec AS total_time_sec,
    r.mean_time_sec AS mean_time_sec,
    r.trace_support_count AS trace_support_count,
    r.support AS support,
    r.trace_count AS trace_count,
    r.course_id AS course_id
ORDER BY freq DESC, source ASC, target ASC
""".strip()


def _format_node_label(code: str) -> str:
    return _HLE_LABELS.get(code, code.replace("_", " ").capitalize())


def _build_window_summaries(profiles: list[dict[str, Any]]) -> list[WindowSummary]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for prof in profiles:
        grouped[(prof["granularity"], prof["window_id"])].append(prof)

    summaries: list[WindowSummary] = []
    for (granularity, window_id), items in grouped.items():
        first = items[0]
        clusters = {str(p["clustering"]["cluster_id"]) for p in items}
        transitions = sum(1 for p in items if p["clustering"].get("transition_detected"))
        summaries.append(
            WindowSummary(
                granularity=granularity,
                window_id=window_id,
                window_start=first["window_start"],
                window_end=first["window_end"],
                student_count=len(items),
                transition_count=transitions,
                cluster_count=len(clusters),
            )
        )
    summaries.sort(key=lambda w: (w.granularity, w.window_start, w.window_id))
    return summaries


def build_cluster_evolution(
    *,
    run_id: str,
    granularity: str,
    course_id: str | None,
    profiles: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> ClusterEvolutionResponse:
    if not profiles:
        return ClusterEvolutionResponse(run_id=run_id, granularity=granularity, course_id=course_id)

    resolved_course = course_id or str(profiles[0]["course_id"])
    snap_by_window: dict[str, dict[str, dict[str, float]]] = {
        str(snap["window_id"]): dict(snap.get("centroids") or {}) for snap in snapshots
    }

    by_window: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prof in profiles:
        by_window[str(prof["window_id"])].append(prof)
        by_student[str(prof["student_id"])].append(prof)

    ordered_windows = sorted(
        by_window.items(),
        key=lambda kv: (kv[1][0]["window_start"], kv[0]),
    )

    distributions: list[WindowClusterDistribution] = []
    sankey_nodes_map: dict[str, SankeyNode] = {}

    for window_id, items in ordered_windows:
        counts: dict[str, int] = defaultdict(int)
        transitions = 0
        for prof in items:
            cid = str(prof["clustering"]["cluster_id"])
            counts[cid] += 1
            if prof["clustering"].get("transition_detected"):
                transitions += 1
            node_id = f"{window_id}::C{cid}"
            if node_id not in sankey_nodes_map:
                label = "Outlier (-1)" if cid == "-1" else f"Clúster {cid}"
                sankey_nodes_map[node_id] = SankeyNode(
                    id=node_id,
                    name=f"{window_id} · {label}",
                    window_id=window_id,
                    cluster_id=cid,
                )

        distributions.append(
            WindowClusterDistribution(
                window_id=window_id,
                window_start=items[0]["window_start"],
                window_end=items[0]["window_end"],
                counts=dict(sorted(counts.items())),
                total_students=len(items),
                transition_count=transitions,
                centroids=snap_by_window.get(window_id, {}),
            )
        )

    link_counts: dict[tuple[str, str], int] = defaultdict(int)
    for items in by_student.values():
        ordered_items = sorted(items, key=lambda p: (p["window_start"], p["window_id"]))
        for prev_item, next_item in itertools.pairwise(ordered_items):
            src = f"{prev_item['window_id']}::C{prev_item['clustering']['cluster_id']}"
            dst = f"{next_item['window_id']}::C{next_item['clustering']['cluster_id']}"
            link_counts[(src, dst)] += 1

    sankey_links = [
        SankeyLink(source=src, target=dst, value=val)
        for (src, dst), val in sorted(link_counts.items())
    ]

    return ClusterEvolutionResponse(
        run_id=run_id,
        granularity=granularity,
        course_id=resolved_course,
        windows=distributions,
        sankey_nodes=list(sankey_nodes_map.values()),
        sankey_links=sankey_links,
    )


def _node_sort_key(node: DfgNode) -> tuple[int, str]:
    if node.code == "START":
        return (0, node.code)
    if node.code == "END":
        return (2, node.code)
    return (1, node.code)


def build_dfg_response_from_rows(
    *,
    run_id: str,
    granularity: str,
    window_id: str,
    scope: GraphScope,
    scope_id: str,
    rows: list[dict[str, Any]],
) -> DfgGraphResponse:
    if not rows:
        return DfgGraphResponse(
            run_id=run_id,
            course_id=None,
            granularity=granularity,
            window_id=window_id,
            scope=scope,
            scope_id=scope_id,
            trace_count=0,
        )

    nodes_map: dict[str, DfgNode] = {}
    edges: list[DfgEdge] = []
    trace_count = int(rows[0].get("trace_count") or 0)
    course_id = str(rows[0].get("course_id") or "")

    for row in rows:
        src_code = str(row["source"])
        dst_code = str(row["target"])
        src_kind: NodeKind = "boundary" if row["source_kind"] == "boundary" else "activity"
        dst_kind: NodeKind = "boundary" if row["target_kind"] == "boundary" else "activity"
        if src_code not in nodes_map:
            default_src_cat = "boundary" if src_kind == "boundary" else "hle"
            nodes_map[src_code] = DfgNode(
                code=src_code,
                label=str(row.get("src_label") or _format_node_label(src_code)),
                kind=src_kind,
                category=str(row.get("src_category") or default_src_cat),
            )
        if dst_code not in nodes_map:
            default_dst_cat = "boundary" if dst_kind == "boundary" else "hle"
            nodes_map[dst_code] = DfgNode(
                code=dst_code,
                label=str(row.get("dst_label") or _format_node_label(dst_code)),
                kind=dst_kind,
                category=str(row.get("dst_category") or default_dst_cat),
            )
        edges.append(
            DfgEdge(
                source=src_code,
                target=dst_code,
                source_kind=src_kind,
                target_kind=dst_kind,
                freq=int(row["freq"]),
                total_time_sec=float(row["total_time_sec"]),
                mean_time_sec=float(row["mean_time_sec"]),
                trace_support_count=int(row["trace_support_count"]),
                support=float(row["support"]),
            )
        )

    return DfgGraphResponse(
        run_id=run_id,
        course_id=course_id or None,
        granularity=granularity,
        window_id=window_id,
        scope=scope,
        scope_id=scope_id,
        trace_count=trace_count,
        nodes=sorted(nodes_map.values(), key=_node_sort_key),
        edges=edges,
    )


class QueryRepository(ABC):
    @abstractmethod
    async def ensure_demo_users(self) -> None: ...

    @abstractmethod
    async def get_user_by_username(self, username: str) -> UserRecord | None: ...

    @abstractmethod
    async def list_courses(self) -> list[CourseSummary]: ...

    @abstractmethod
    async def list_runs(self, *, course_id: str | None = None) -> list[RunSummary]: ...

    @abstractmethod
    async def list_windows(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
        course_id: str | None = None,
    ) -> list[WindowSummary]: ...

    @abstractmethod
    async def get_cluster_evolution(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> ClusterEvolutionResponse: ...

    @abstractmethod
    async def list_cluster_students(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        cluster_id: int,
        course_id: str | None = None,
    ) -> list[ClusterStudentItem]: ...

    @abstractmethod
    async def list_students(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> list[StudentListItem]: ...

    @abstractmethod
    async def get_student_timeline(
        self,
        *,
        run_id: str,
        student_id: str,
        granularity: str,
    ) -> StudentTimelineResponse: ...

    @abstractmethod
    async def get_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: GraphScope,
        scope_id: str,
    ) -> DfgGraphResponse: ...

    @abstractmethod
    async def list_experiment_metrics(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
    ) -> list[ExperimentMetricRecord]: ...

    @abstractmethod
    async def close(self) -> None: ...


class PolyglotQueryRepository(QueryRepository):
    """Repositorio de lectura sobre PostgreSQL, MongoDB y Neo4j (ADR-03, RF-15)."""

    def __init__(
        self,
        *,
        postgres_dsn: str,
        mongo_uri: str,
        mongo_db: str,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
    ) -> None:
        self._postgres_dsn = postgres_dsn
        self._mongo_uri = mongo_uri
        self._mongo_db = mongo_db
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._pg_pool: asyncpg.Pool | None = None
        self._mongo_client: AsyncMongoClient | None = None
        self._neo4j_driver: AsyncDriver | None = None
        self._lock = asyncio.Lock()

    async def _get_pg_pool(self) -> asyncpg.Pool:
        if self._pg_pool is None:
            async with self._lock:
                if self._pg_pool is None:
                    import asyncpg

                    self._pg_pool = await asyncpg.create_pool(
                        self._postgres_dsn,
                        min_size=1,
                        max_size=5,
                    )
        return self._pg_pool

    async def _get_mongo(self) -> AsyncMongoClient:
        if self._mongo_client is None:
            async with self._lock:
                if self._mongo_client is None:
                    from pymongo import AsyncMongoClient

                    self._mongo_client = AsyncMongoClient(self._mongo_uri, tz_aware=True)
        return self._mongo_client

    async def _get_neo4j(self) -> AsyncDriver:
        if self._neo4j_driver is None:
            async with self._lock:
                if self._neo4j_driver is None:
                    from neo4j import AsyncGraphDatabase

                    self._neo4j_driver = AsyncGraphDatabase.driver(
                        self._neo4j_uri,
                        auth=(self._neo4j_user, self._neo4j_password),
                    )
        return self._neo4j_driver

    async def ensure_demo_users(self) -> None:
        pool = await self._get_pg_pool()
        users = build_demo_user_records()
        async with pool.acquire() as conn, conn.transaction():
            for user in users:
                await conn.execute(
                    """
                    INSERT INTO users_roles (
                        user_id, username, password_hash, role, assigned_courses_json
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (username) DO NOTHING
                    """,
                    user.user_id,
                    user.username,
                    user.password_hash,
                    user.role,
                    json.dumps(user.assigned_courses),
                )

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        pool = await self._get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, username, password_hash, role, assigned_courses_json
                FROM users_roles
                WHERE username = $1
                """,
                username,
            )
        if row is None:
            return None
        assigned = row["assigned_courses_json"]
        if isinstance(assigned, str):
            assigned = json.loads(assigned)
        return UserRecord(
            user_id=row["user_id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
            assigned_courses=list(assigned or []),
        )

    async def list_courses(self) -> list[CourseSummary]:
        pool = await self._get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT course_id, external_code, title, start_date, end_date
                FROM courses
                ORDER BY course_id ASC
                """
            )
        courses = [
            CourseSummary(
                course_id=row["course_id"],
                external_code=row["external_code"],
                title=row["title"],
                start_date=row["start_date"],
                end_date=row["end_date"],
            )
            for row in rows
        ]
        known_ids = {c.course_id for c in courses}
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        mongo_courses = await db["student_profiles"].distinct("course_id")
        for cid in sorted(str(c) for c in mongo_courses if c):
            if cid not in known_ids:
                courses.append(CourseSummary(course_id=cid, title=f"Curso {cid}"))
        return courses

    async def list_runs(self, *, course_id: str | None = None) -> list[RunSummary]:
        pool = await self._get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.run_id, r.mode, r.status, r.source_dataset, r.speed_factor,
                       r.events_processed, r.started_at, r.finished_at,
                       rc.clustering_algorithm, rc.active_granularities_json
                FROM runs r
                LEFT JOIN run_configs rc ON rc.run_id = r.run_id
                ORDER BY r.started_at DESC
                """
            )

        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        summaries: list[RunSummary] = []
        seen_run_ids: set[str] = set()

        for row in rows:
            run_id = row["run_id"]
            seen_run_ids.add(run_id)
            run_courses = sorted(
                str(c)
                for c in await db["student_profiles"].distinct("course_id", {"run_id": run_id})
                if c
            )
            if course_id and course_id not in run_courses:
                continue
            grans = row["active_granularities_json"]
            if isinstance(grans, str):
                grans = json.loads(grans)
            summaries.append(
                RunSummary(
                    run_id=run_id,
                    mode=row["mode"],
                    status=row["status"],
                    source_dataset=row["source_dataset"],
                    speed_factor=row["speed_factor"],
                    events_processed=row["events_processed"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                    clustering_algorithm=row["clustering_algorithm"],
                    active_granularities=list(grans or []),
                    course_ids=run_courses,
                )
            )

        mongo_runs = await db["student_profiles"].distinct("run_id")
        for run_id in sorted(str(r) for r in mongo_runs if r):
            if run_id in seen_run_ids:
                continue
            run_courses = sorted(
                str(c)
                for c in await db["student_profiles"].distinct("course_id", {"run_id": run_id})
                if c
            )
            if course_id and course_id not in run_courses:
                continue
            summaries.append(
                RunSummary(
                    run_id=run_id,
                    mode="stream",
                    status="completed",
                    source_dataset="kafka",
                    course_ids=run_courses,
                )
            )
        return summaries

    async def list_windows(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
        course_id: str | None = None,
    ) -> list[WindowSummary]:
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        query: dict[str, Any] = {"run_id": run_id}
        if granularity:
            query["granularity"] = granularity
        if course_id:
            query["course_id"] = course_id
        profiles = await db["student_profiles"].find(query).to_list(length=None)
        return _build_window_summaries(profiles)

    async def get_cluster_evolution(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> ClusterEvolutionResponse:
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        query: dict[str, Any] = {"run_id": run_id, "granularity": granularity}
        if course_id:
            query["course_id"] = course_id
        profiles = await db["student_profiles"].find(query).to_list(length=None)
        snapshots = await db["cluster_snapshots"].find(query).to_list(length=None)
        return build_cluster_evolution(
            run_id=run_id,
            granularity=granularity,
            course_id=course_id,
            profiles=profiles,
            snapshots=snapshots,
        )

    async def list_cluster_students(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        cluster_id: int,
        course_id: str | None = None,
    ) -> list[ClusterStudentItem]:
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        query: dict[str, Any] = {
            "run_id": run_id,
            "granularity": granularity,
            "window_id": window_id,
            "clustering.cluster_id": cluster_id,
        }
        if course_id:
            query["course_id"] = course_id
        docs = await db["student_profiles"].find(query).to_list(length=None)
        items = [
            ClusterStudentItem(
                student_id=doc["student_id"],
                cluster_id=int(doc["clustering"]["cluster_id"]),
                previous_cluster_id=doc["clustering"].get("previous_cluster_id"),
                transition_detected=bool(doc["clustering"].get("transition_detected", False)),
                distance_to_centroid=doc["clustering"].get("distance_to_centroid"),
                is_outlier=bool(doc["clustering"].get("is_outlier", False)),
                features=dict(doc.get("features") or {}),
                top_contributing_features=[
                    ExplainabilityFeature.model_validate(item)
                    for item in doc.get("explainability", {}).get("top_contributing_features", [])
                ],
            )
            for doc in docs
        ]
        items.sort(key=lambda s: s.student_id)
        return items

    async def list_students(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> list[StudentListItem]:
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        query: dict[str, Any] = {"run_id": run_id, "granularity": granularity}
        if course_id:
            query["course_id"] = course_id
        docs = await db["student_profiles"].find(query).to_list(length=None)
        by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for doc in docs:
            by_student[str(doc["student_id"])].append(doc)
        result: list[StudentListItem] = []
        for sid, items in sorted(by_student.items()):
            ordered = sorted(items, key=lambda d: (d["window_start"], d["window_id"]))
            latest = ordered[-1]
            result.append(
                StudentListItem(
                    student_id=sid,
                    latest_window_id=str(latest["window_id"]),
                    latest_cluster_id=int(latest["clustering"]["cluster_id"]),
                    transition_count=sum(
                        1 for d in ordered if d["clustering"].get("transition_detected")
                    ),
                    total_windows=len(ordered),
                )
            )
        return result

    async def get_student_timeline(
        self,
        *,
        run_id: str,
        student_id: str,
        granularity: str,
    ) -> StudentTimelineResponse:
        mongo = await self._get_mongo()
        db = mongo[self._mongo_db]
        docs = (
            await db["student_profiles"]
            .find({"run_id": run_id, "student_id": student_id, "granularity": granularity})
            .to_list(length=None)
        )
        ordered = sorted(docs, key=lambda d: (d["window_start"], d["window_id"]))
        course_id = str(ordered[0]["course_id"]) if ordered else None
        history = [
            StudentWindowEntry(
                window_id=str(doc["window_id"]),
                window_start=doc["window_start"],
                window_end=doc["window_end"],
                algorithm=str(doc["clustering"]["algorithm"]),
                cluster_id=int(doc["clustering"]["cluster_id"]),
                previous_cluster_id=doc["clustering"].get("previous_cluster_id"),
                transition_detected=bool(doc["clustering"].get("transition_detected", False)),
                distance_to_centroid=doc["clustering"].get("distance_to_centroid"),
                is_outlier=bool(doc["clustering"].get("is_outlier", False)),
                features=dict(doc.get("features") or {}),
                top_contributing_features=[
                    ExplainabilityFeature.model_validate(item)
                    for item in doc.get("explainability", {}).get("top_contributing_features", [])
                ],
                ingested_to_profile_ms=int(
                    doc.get("latencies_ms", {}).get("ingested_to_profile", 0)
                ),
            )
            for doc in ordered
        ]
        return StudentTimelineResponse(
            run_id=run_id,
            course_id=course_id,
            granularity=granularity,
            student_id=student_id,
            history=history,
        )

    async def get_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: GraphScope,
        scope_id: str,
    ) -> DfgGraphResponse:
        driver = await self._get_neo4j()
        async with driver.session() as session:
            result = await session.run(
                _NEO4J_READ_DFG_CYPHER,
                run_id=run_id,
                granularity=granularity,
                window_id=window_id,
                scope=scope,
                scope_id=scope_id,
            )
            rows = await result.data()
        return build_dfg_response_from_rows(
            run_id=run_id,
            granularity=granularity,
            window_id=window_id,
            scope=scope,
            scope_id=scope_id,
            rows=rows,
        )

    async def list_experiment_metrics(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
    ) -> list[ExperimentMetricRecord]:
        pool = await self._get_pg_pool()
        async with pool.acquire() as conn:
            if granularity:
                rows = await conn.fetch(
                    """
                    SELECT metric_id, run_id, granularity, window_id,
                           silhouette_score, ari_score, pm_fitness, pm_precision,
                           p50_latency_ms, p95_latency_ms, p99_latency_ms,
                           throughput_eps, computed_at
                    FROM experiment_metrics
                    WHERE run_id = $1 AND granularity = $2
                    ORDER BY window_id ASC, metric_id ASC
                    """,
                    run_id,
                    granularity,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT metric_id, run_id, granularity, window_id,
                           silhouette_score, ari_score, pm_fitness, pm_precision,
                           p50_latency_ms, p95_latency_ms, p99_latency_ms,
                           throughput_eps, computed_at
                    FROM experiment_metrics
                    WHERE run_id = $1
                    ORDER BY granularity ASC, window_id ASC, metric_id ASC
                    """,
                    run_id,
                )
        return [
            ExperimentMetricRecord(
                metric_id=row["metric_id"],
                run_id=row["run_id"],
                granularity=row["granularity"],
                window_id=row["window_id"],
                silhouette_score=row["silhouette_score"],
                ari_score=row["ari_score"],
                pm_fitness=row["pm_fitness"],
                pm_precision=row["pm_precision"],
                p50_latency_ms=row["p50_latency_ms"],
                p95_latency_ms=row["p95_latency_ms"],
                p99_latency_ms=row["p99_latency_ms"],
                throughput_eps=row["throughput_eps"],
                computed_at=row["computed_at"],
            )
            for row in rows
        ]

    async def close(self) -> None:
        if self._pg_pool is not None:
            await self._pg_pool.close()
            self._pg_pool = None
        if self._mongo_client is not None:
            await self._mongo_client.close()
            self._mongo_client = None
        if self._neo4j_driver is not None:
            await self._neo4j_driver.close()
            self._neo4j_driver = None


class InMemoryQueryRepository(QueryRepository):
    """Repositorio en memoria para pruebas unitarias rápidas de C7."""

    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}
        self.courses: dict[str, CourseSummary] = {}
        self.runs: dict[str, RunSummary] = {}
        self.profiles: list[StudentProfileDocument] = []
        self.snapshots: list[ClusterSnapshotDocument] = []
        self.graphs: dict[tuple[str, str, str, str, str], DfgGraphDocument] = {}
        self.metrics: list[ExperimentMetricRecord] = []

    async def ensure_demo_users(self) -> None:
        for user in build_demo_user_records():
            self.users.setdefault(user.username, user)

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        return self.users.get(username)

    async def list_courses(self) -> list[CourseSummary]:
        result = dict(self.courses)
        for prof in self.profiles:
            if prof.course_id not in result:
                result[prof.course_id] = CourseSummary(
                    course_id=prof.course_id,
                    title=f"Curso {prof.course_id}",
                )
        return sorted(result.values(), key=lambda c: c.course_id)

    async def list_runs(self, *, course_id: str | None = None) -> list[RunSummary]:
        runs_list = list(self.runs.values())
        if course_id:
            runs_list = [r for r in runs_list if course_id in r.course_ids]
        runs_list.sort(
            key=lambda r: r.started_at or datetime.min,
            reverse=True,
        )
        return runs_list

    def _profile_dicts(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
        course_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            p.to_mongo_doc()
            for p in self.profiles
            if p.run_id == run_id
            and (granularity is None or p.granularity == granularity)
            and (course_id is None or p.course_id == course_id)
        ]

    async def list_windows(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
        course_id: str | None = None,
    ) -> list[WindowSummary]:
        return _build_window_summaries(
            self._profile_dicts(run_id=run_id, granularity=granularity, course_id=course_id)
        )

    async def get_cluster_evolution(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> ClusterEvolutionResponse:
        snaps = [
            s.to_mongo_doc()
            for s in self.snapshots
            if s.run_id == run_id
            and s.granularity == granularity
            and (course_id is None or s.course_id == course_id)
        ]
        return build_cluster_evolution(
            run_id=run_id,
            granularity=granularity,
            course_id=course_id,
            profiles=self._profile_dicts(
                run_id=run_id,
                granularity=granularity,
                course_id=course_id,
            ),
            snapshots=snaps,
        )

    async def list_cluster_students(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        cluster_id: int,
        course_id: str | None = None,
    ) -> list[ClusterStudentItem]:
        items = [
            ClusterStudentItem(
                student_id=p.student_id,
                cluster_id=p.clustering.cluster_id,
                previous_cluster_id=p.clustering.previous_cluster_id,
                transition_detected=p.clustering.transition_detected,
                distance_to_centroid=p.clustering.distance_to_centroid,
                is_outlier=p.clustering.is_outlier,
                features=dict(p.features),
                top_contributing_features=list(p.explainability.top_contributing_features),
            )
            for p in self.profiles
            if p.run_id == run_id
            and p.granularity == granularity
            and p.window_id == window_id
            and p.clustering.cluster_id == cluster_id
            and (course_id is None or p.course_id == course_id)
        ]
        items.sort(key=lambda s: s.student_id)
        return items

    async def list_students(
        self,
        *,
        run_id: str,
        granularity: str,
        course_id: str | None = None,
    ) -> list[StudentListItem]:
        by_student: dict[str, list[StudentProfileDocument]] = defaultdict(list)
        for p in self.profiles:
            if (
                p.run_id == run_id
                and p.granularity == granularity
                and (course_id is None or p.course_id == course_id)
            ):
                by_student[p.student_id].append(p)
        result: list[StudentListItem] = []
        for sid, docs in sorted(by_student.items()):
            ordered = sorted(docs, key=lambda d: (d.window_start, d.window_id))
            latest = ordered[-1]
            result.append(
                StudentListItem(
                    student_id=sid,
                    latest_window_id=latest.window_id,
                    latest_cluster_id=latest.clustering.cluster_id,
                    transition_count=sum(1 for d in ordered if d.clustering.transition_detected),
                    total_windows=len(ordered),
                )
            )
        return result

    async def get_student_timeline(
        self,
        *,
        run_id: str,
        student_id: str,
        granularity: str,
    ) -> StudentTimelineResponse:
        docs = sorted(
            (
                p
                for p in self.profiles
                if p.run_id == run_id
                and p.student_id == student_id
                and p.granularity == granularity
            ),
            key=lambda d: (d.window_start, d.window_id),
        )
        course_id = docs[0].course_id if docs else None
        return StudentTimelineResponse(
            run_id=run_id,
            course_id=course_id,
            granularity=granularity,
            student_id=student_id,
            history=[
                StudentWindowEntry(
                    window_id=p.window_id,
                    window_start=p.window_start,
                    window_end=p.window_end,
                    algorithm=p.clustering.algorithm,
                    cluster_id=p.clustering.cluster_id,
                    previous_cluster_id=p.clustering.previous_cluster_id,
                    transition_detected=p.clustering.transition_detected,
                    distance_to_centroid=p.clustering.distance_to_centroid,
                    is_outlier=p.clustering.is_outlier,
                    features=dict(p.features),
                    top_contributing_features=list(p.explainability.top_contributing_features),
                    ingested_to_profile_ms=p.latencies_ms.ingested_to_profile,
                )
                for p in docs
            ],
        )

    async def get_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: GraphScope,
        scope_id: str,
    ) -> DfgGraphResponse:
        doc = self.graphs.get((run_id, granularity, window_id, scope, scope_id))
        if doc is None:
            return DfgGraphResponse(
                run_id=run_id,
                granularity=granularity,
                window_id=window_id,
                scope=scope,
                scope_id=scope_id,
                trace_count=0,
            )
        return DfgGraphResponse(
            run_id=doc.run_id,
            course_id=doc.course_id,
            granularity=doc.granularity,
            window_id=doc.window_id,
            scope=doc.scope,
            scope_id=doc.scope_id,
            trace_count=doc.trace_count,
            nodes=list(doc.nodes),
            edges=list(doc.edges),
        )

    async def list_experiment_metrics(
        self,
        *,
        run_id: str,
        granularity: str | None = None,
    ) -> list[ExperimentMetricRecord]:
        return [
            m
            for m in self.metrics
            if m.run_id == run_id and (granularity is None or m.granularity == granularity)
        ]

    async def close(self) -> None:
        return None
