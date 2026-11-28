from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from dsm_common.schemas import DfgGraphDocument

if TYPE_CHECKING:
    from neo4j import AsyncDriver

CONSTRAINT_STATEMENTS: tuple[str, ...] = (
    (
        "CREATE CONSTRAINT activity_unique IF NOT EXISTS "
        "FOR (a:Activity) REQUIRE (a.course_id, a.hle_code) IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT boundary_unique IF NOT EXISTS "
        "FOR (b:Boundary) REQUIRE (b.course_id, b.name) IS UNIQUE"
    ),
    (
        "CREATE INDEX dfg_lookup IF NOT EXISTS "
        "FOR ()-[r:DFG]-() ON (r.run_id, r.granularity, r.window_id, r.scope, r.scope_id)"
    ),
)

_DELETE_DFG_CYPHER = """
MATCH ()-[r:DFG {
    run_id: $run_id,
    granularity: $granularity,
    window_id: $window_id,
    scope: $scope,
    scope_id: $scope_id
}]->()
DELETE r
""".strip()

_MERGE_ACTIVITIES_CYPHER = """
UNWIND $nodes AS node
MERGE (a:Activity {course_id: $course_id, hle_code: node.code})
SET a.label = node.label,
    a.category = node.category
""".strip()

_MERGE_BOUNDARIES_CYPHER = """
UNWIND $nodes AS node
MERGE (b:Boundary {course_id: $course_id, name: node.code})
SET b.label = node.label
""".strip()

_FETCH_DFG_CYPHER = """
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
    CASE WHEN dst:Boundary THEN dst.name ELSE dst.hle_code END AS target,
    CASE WHEN dst:Boundary THEN 'boundary' ELSE 'activity' END AS target_kind,
    r.freq AS freq,
    r.total_time_sec AS total_time_sec,
    r.mean_time_sec AS mean_time_sec,
    r.trace_support_count AS trace_support_count,
    r.support AS support,
    r.trace_count AS trace_count
ORDER BY freq DESC, source ASC, target ASC
""".strip()


def _build_create_edges_cypher(source_kind: str, target_kind: str) -> str:
    src_match = (
        "(src:Boundary {course_id: $course_id, name: edge.source})"
        if source_kind == "boundary"
        else "(src:Activity {course_id: $course_id, hle_code: edge.source})"
    )
    dst_match = (
        "(dst:Boundary {course_id: $course_id, name: edge.target})"
        if target_kind == "boundary"
        else "(dst:Activity {course_id: $course_id, hle_code: edge.target})"
    )
    return (
        f"UNWIND $edges AS edge\n"
        f"MATCH {src_match}\n"
        f"MATCH {dst_match}\n"
        "CREATE (src)-[r:DFG {\n"
        "    run_id: $run_id,\n"
        "    course_id: $course_id,\n"
        "    granularity: $granularity,\n"
        "    window_id: $window_id,\n"
        "    scope: $scope,\n"
        "    scope_id: $scope_id,\n"
        "    freq: edge.freq,\n"
        "    total_time_sec: edge.total_time_sec,\n"
        "    mean_time_sec: edge.mean_time_sec,\n"
        "    trace_support_count: edge.trace_support_count,\n"
        "    support: edge.support,\n"
        "    trace_count: $trace_count,\n"
        "    algorithm: $algorithm,\n"
        "    ingested_to_graph_ms: $ingested_to_graph_ms,\n"
        "    updated_at: $updated_at\n"
        "}]->(dst)"
    )


_CREATE_EDGES_CYPHER: dict[tuple[str, str], str] = {
    ("boundary", "activity"): _build_create_edges_cypher("boundary", "activity"),
    ("activity", "activity"): _build_create_edges_cypher("activity", "activity"),
    ("activity", "boundary"): _build_create_edges_cypher("activity", "boundary"),
    ("boundary", "boundary"): _build_create_edges_cypher("boundary", "boundary"),
}


class GraphRepository(ABC):
    @abstractmethod
    async def ensure_constraints(self) -> None: ...

    @abstractmethod
    async def upsert_dfg(self, graph: DfgGraphDocument) -> None: ...

    @abstractmethod
    async def delete_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> None: ...

    @abstractmethod
    async def fetch_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def close(self) -> None: ...


class Neo4jGraphRepository(GraphRepository):
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        database: str | None = None,
        driver: AsyncDriver | None = None,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver: AsyncDriver | None = driver
        self._driver_lock = asyncio.Lock()

    async def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            async with self._driver_lock:
                if self._driver is None:
                    from neo4j import AsyncGraphDatabase

                    self._driver = AsyncGraphDatabase.driver(
                        self._uri,
                        auth=(self._user, self._password),
                    )
        return self._driver

    async def ensure_constraints(self) -> None:
        driver = await self._get_driver()
        async with driver.session(database=self._database) as session:
            for statement in CONSTRAINT_STATEMENTS:
                result = await session.run(statement)
                await result.consume()

    async def upsert_dfg(self, graph: DfgGraphDocument) -> None:
        driver = await self._get_driver()
        activity_nodes = [
            {"code": node.code, "label": node.label, "category": node.category}
            for node in graph.nodes
            if node.kind == "activity"
        ]
        boundary_nodes = [
            {"code": node.code, "label": node.label}
            for node in graph.nodes
            if node.kind == "boundary"
        ]
        grouped_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for edge in graph.edges:
            key = (edge.source_kind, edge.target_kind)
            grouped_edges.setdefault(key, []).append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "freq": edge.freq,
                    "total_time_sec": edge.total_time_sec,
                    "mean_time_sec": edge.mean_time_sec,
                    "trace_support_count": edge.trace_support_count,
                    "support": edge.support,
                }
            )

        scope_params = {
            "run_id": graph.run_id,
            "granularity": graph.granularity,
            "window_id": graph.window_id,
            "scope": graph.scope,
            "scope_id": graph.scope_id,
        }
        updated_at_iso = graph.updated_at.isoformat()

        async def _write_tx(tx: Any) -> None:
            res = await tx.run(_DELETE_DFG_CYPHER, **scope_params)
            await res.consume()

            if activity_nodes:
                res = await tx.run(
                    _MERGE_ACTIVITIES_CYPHER,
                    course_id=graph.course_id,
                    nodes=activity_nodes,
                )
                await res.consume()

            if boundary_nodes:
                res = await tx.run(
                    _MERGE_BOUNDARIES_CYPHER,
                    course_id=graph.course_id,
                    nodes=boundary_nodes,
                )
                await res.consume()

            for pair, edges in grouped_edges.items():
                cypher = _CREATE_EDGES_CYPHER[pair]
                res = await tx.run(
                    cypher,
                    **scope_params,
                    course_id=graph.course_id,
                    trace_count=graph.trace_count,
                    algorithm=graph.algorithm,
                    ingested_to_graph_ms=graph.ingested_to_graph_ms,
                    updated_at=updated_at_iso,
                    edges=edges,
                )
                await res.consume()

        async with driver.session(database=self._database) as session:
            await session.execute_write(_write_tx)

    async def delete_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> None:
        driver = await self._get_driver()

        async def _delete_tx(tx: Any) -> None:
            res = await tx.run(
                _DELETE_DFG_CYPHER,
                run_id=run_id,
                granularity=granularity,
                window_id=window_id,
                scope=scope,
                scope_id=scope_id,
            )
            await res.consume()

        async with driver.session(database=self._database) as session:
            await session.execute_write(_delete_tx)

    async def fetch_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> list[dict[str, Any]]:
        driver = await self._get_driver()

        async def _read_tx(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                _FETCH_DFG_CYPHER,
                run_id=run_id,
                granularity=granularity,
                window_id=window_id,
                scope=scope,
                scope_id=scope_id,
            )
            return await result.data()

        async with driver.session(database=self._database) as session:
            return await session.execute_read(_read_tx)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None


class InMemoryGraphRepository(GraphRepository):
    def __init__(self) -> None:
        self.constraints_ensured = False
        self.graphs: dict[tuple[str, str, str, str, str], DfgGraphDocument] = {}

    @staticmethod
    def make_key(
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> tuple[str, str, str, str, str]:
        return (run_id, granularity, window_id, scope, scope_id)

    async def ensure_constraints(self) -> None:
        self.constraints_ensured = True

    async def upsert_dfg(self, graph: DfgGraphDocument) -> None:
        key = self.make_key(
            run_id=graph.run_id,
            granularity=graph.granularity,
            window_id=graph.window_id,
            scope=graph.scope,
            scope_id=graph.scope_id,
        )
        self.graphs[key] = graph

    async def delete_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> None:
        key = self.make_key(
            run_id=run_id,
            granularity=granularity,
            window_id=window_id,
            scope=scope,
            scope_id=scope_id,
        )
        self.graphs.pop(key, None)

    async def fetch_dfg(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        scope: str,
        scope_id: str,
    ) -> list[dict[str, Any]]:
        key = self.make_key(
            run_id=run_id,
            granularity=granularity,
            window_id=window_id,
            scope=scope,
            scope_id=scope_id,
        )
        graph = self.graphs.get(key)
        if graph is None:
            return []
        rows = [
            {
                "source": edge.source,
                "source_kind": edge.source_kind,
                "target": edge.target,
                "target_kind": edge.target_kind,
                "freq": edge.freq,
                "total_time_sec": edge.total_time_sec,
                "mean_time_sec": edge.mean_time_sec,
                "trace_support_count": edge.trace_support_count,
                "support": edge.support,
                "trace_count": graph.trace_count,
            }
            for edge in graph.edges
        ]
        rows.sort(key=lambda r: (-r["freq"], r["source"], r["target"]))
        return rows

    async def close(self) -> None:
        return None
