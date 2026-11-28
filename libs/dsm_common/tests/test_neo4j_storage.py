from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dsm_common.schemas import DfgEdge, DfgGraphDocument, DfgNode
from dsm_common.storage import InMemoryGraphRepository, Neo4jGraphRepository


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeTx:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    async def run(self, query: str, **params: Any) -> _FakeResult:
        self._calls.append((query, params))
        if "RETURN" in query:
            return _FakeResult(
                [
                    {
                        "source": "START",
                        "source_kind": "boundary",
                        "target": "ACCESO_CURSO",
                        "target_kind": "activity",
                        "freq": 2,
                        "total_time_sec": 0.0,
                        "mean_time_sec": 0.0,
                        "trace_support_count": 2,
                        "support": 1.0,
                        "trace_count": 2,
                    }
                ]
            )
        return _FakeResult()


class _FakeSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def run(self, query: str, **params: Any) -> _FakeResult:
        self._calls.append((query, params))
        return _FakeResult()

    async def execute_write(self, fn: Any) -> Any:
        return await fn(_FakeTx(self._calls))

    async def execute_read(self, fn: Any) -> Any:
        return await fn(_FakeTx(self._calls))


class _FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def session(self, **_kwargs: Any) -> _FakeSession:
        return _FakeSession(self.calls)

    async def close(self) -> None:
        self.closed = True


def _sample_graph() -> DfgGraphDocument:
    now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    return DfgGraphDocument(
        run_id="r1",
        course_id="c1",
        granularity="weekly",
        window_id="2024-W36",
        window_start=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 9, 9, 0, 0, tzinfo=UTC),
        scope="cluster",
        scope_id="0",
        algorithm="dfg",
        trace_count=2,
        nodes=[
            DfgNode(code="START", label="Inicio", kind="boundary", category="boundary"),
            DfgNode(
                code="ACCESO_CURSO",
                label="Acceso al curso",
                kind="activity",
                category="hle",
            ),
            DfgNode(
                code="CONSULTA_RECURSO",
                label="Consulta de recurso",
                kind="activity",
                category="hle",
            ),
            DfgNode(code="END", label="Fin", kind="boundary", category="boundary"),
        ],
        edges=[
            DfgEdge(
                source="START",
                target="ACCESO_CURSO",
                source_kind="boundary",
                target_kind="activity",
                freq=2,
                total_time_sec=0.0,
                mean_time_sec=0.0,
                trace_support_count=2,
                support=1.0,
            ),
            DfgEdge(
                source="ACCESO_CURSO",
                target="CONSULTA_RECURSO",
                source_kind="activity",
                target_kind="activity",
                freq=2,
                total_time_sec=30.0,
                mean_time_sec=15.0,
                trace_support_count=2,
                support=1.0,
            ),
            DfgEdge(
                source="CONSULTA_RECURSO",
                target="END",
                source_kind="activity",
                target_kind="boundary",
                freq=2,
                total_time_sec=0.0,
                mean_time_sec=0.0,
                trace_support_count=2,
                support=1.0,
            ),
        ],
        ingested_to_graph_ms=14,
        updated_at=now,
    )


async def test_in_memory_graph_repository_upsert_fetch_delete() -> None:
    repo = InMemoryGraphRepository()
    await repo.ensure_constraints()
    assert repo.constraints_ensured is True

    graph = _sample_graph()
    await repo.upsert_dfg(graph)
    rows = await repo.fetch_dfg(
        run_id="r1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    assert len(rows) == 3
    assert rows[0]["freq"] == 2
    assert rows[0]["support"] == 1.0

    await repo.delete_dfg(
        run_id="r1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    assert (
        await repo.fetch_dfg(
            run_id="r1",
            granularity="weekly",
            window_id="2024-W36",
            scope="cluster",
            scope_id="0",
        )
        == []
    )
    await repo.close()


async def test_neo4j_graph_repository_cypher_parameters() -> None:
    driver = _FakeDriver()
    repo = Neo4jGraphRepository("bolt://localhost:7687", "neo4j", "pass", driver=driver)

    await repo.ensure_constraints()
    assert len(driver.calls) == 3
    assert "CREATE CONSTRAINT activity_unique" in driver.calls[0][0]
    assert "CREATE CONSTRAINT boundary_unique" in driver.calls[1][0]
    assert "CREATE INDEX dfg_lookup" in driver.calls[2][0]

    driver.calls.clear()
    graph = _sample_graph()
    await repo.upsert_dfg(graph)
    # 1 delete + 1 merge activities + 1 merge boundaries + 3 edge groups
    assert len(driver.calls) == 6
    assert "DELETE r" in driver.calls[0][0]
    assert driver.calls[0][1]["scope_id"] == "0"
    assert "MERGE (a:Activity" in driver.calls[1][0]
    assert len(driver.calls[1][1]["nodes"]) == 2
    assert "MERGE (b:Boundary" in driver.calls[2][0]
    assert len(driver.calls[2][1]["nodes"]) == 2

    edge_queries = [q for q, _ in driver.calls[3:]]
    assert any("(src:Boundary" in q and "(dst:Activity" in q for q in edge_queries)
    assert any("(src:Activity" in q and "(dst:Activity" in q for q in edge_queries)
    assert any("(src:Activity" in q and "(dst:Boundary" in q for q in edge_queries)

    driver.calls.clear()
    fetched = await repo.fetch_dfg(
        run_id="r1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    assert len(fetched) == 1
    assert fetched[0]["source"] == "START"

    driver.calls.clear()
    await repo.delete_dfg(
        run_id="r1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    assert len(driver.calls) == 1
    assert "DELETE r" in driver.calls[0][0]

    await repo.close()
    assert driver.closed is True
