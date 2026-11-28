from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dsm_common.config import ProcessMiningConfig
from dsm_common.schemas import ClusterAssignmentMessage, TraceEventItem, TraceMessage
from dsm_core.process_mining import (
    END_NODE,
    START_NODE,
    PM4PyDFGDiscovery,
    ProcessMiningEngine,
    create_process_discovery,
)


def _item(
    event_id: str,
    hle: str,
    offset_sec: int,
    *,
    base: datetime = datetime(2024, 9, 2, 10, 0, tzinfo=UTC),
) -> TraceEventItem:
    return TraceEventItem(
        event_id=event_id,
        hle=hle,
        t=base + timedelta(seconds=offset_sec),
        a="viewed",
        resource_id=f"res_{event_id}",
        resource_type="resource",
    )


def _trace_msg(
    u: str,
    items: list[TraceEventItem],
    *,
    run_id: str = "r1",
    granularity: str = "weekly",
    window_id: str = "2024-W36",
) -> TraceMessage:
    t0 = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    return TraceMessage(
        run_id=run_id,
        course_id="course_105",
        u=u,
        granularity=granularity,
        window_id=window_id,
        window_start=t0,
        window_end=t0 + timedelta(days=7),
        hle_version="v0.1-provisional",
        trace=items,
        event_count=len(items),
        last_event_ingested_at=now - timedelta(milliseconds=15),
        emitted_at=now,
    )


def _assign_msg(
    u: str,
    cluster_id: int,
    *,
    run_id: str = "r1",
    granularity: str = "weekly",
    window_id: str = "2024-W36",
) -> ClusterAssignmentMessage:
    t0 = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    return ClusterAssignmentMessage(
        run_id=run_id,
        course_id="course_105",
        u=u,
        granularity=granularity,
        window_id=window_id,
        window_start=t0,
        window_end=t0 + timedelta(days=7),
        algorithm="denstream",
        cluster_id=cluster_id,
        last_event_ingested_at=now - timedelta(milliseconds=10),
        emitted_at=now,
    )


def test_pm4py_dfg_discovery_handles_empty_single_and_repeated_edges() -> None:
    discovery = PM4PyDFGDiscovery(include_boundaries=True)

    empty = discovery.build_student_dfg([])
    assert empty.trace_count == 0
    assert empty.edges == {}

    single = discovery.build_student_dfg([_item("e1", "ACCESO_CURSO", 0)])
    assert single.trace_count == 1
    assert single.edges[(START_NODE, "ACCESO_CURSO")].freq == 1
    assert single.edges[("ACCESO_CURSO", END_NODE)].freq == 1

    # Traza desordenada en entrada debe ordenarse por (t, event_id) y registrar auto-bucle + dt=0
    repeated = discovery.build_student_dfg(
        [
            _item("e4", "CONSULTA_RECURSO", 45),
            _item("e2", "CONSULTA_RECURSO", 10),
            _item("e3", "ACCESO_CURSO", 10),  # mismo t que e2 -> (e2, e3) por event_id
            _item("e1", "ACCESO_CURSO", 0),
        ]
    )
    # Ordenado: ACCESO_CURSO(0) -> CONSULTA_RECURSO(10) -> ACCESO_CURSO(10) -> CONSULTA_RECURSO(45)
    ac_edge = repeated.edges[("ACCESO_CURSO", "CONSULTA_RECURSO")]
    assert ac_edge.freq == 2
    assert ac_edge.total_time_sec == pytest.approx(45.0)
    assert ac_edge.trace_support_count == 1
    assert repeated.edges[("CONSULTA_RECURSO", "ACCESO_CURSO")].freq == 1
    assert repeated.edges[("CONSULTA_RECURSO", "ACCESO_CURSO")].total_time_sec == pytest.approx(0.0)


def test_pm4py_dfg_discovery_without_boundaries_and_additive_merge() -> None:
    discovery = PM4PyDFGDiscovery(include_boundaries=False)
    dfg1 = discovery.build_student_dfg(
        [_item("1", "ACCESO_CURSO", 0), _item("2", "CONSULTA_RECURSO", 30)]
    )
    dfg2 = discovery.build_student_dfg(
        [_item("3", "ACCESO_CURSO", 0), _item("4", "CONSULTA_RECURSO", 60)]
    )
    assert START_NODE not in dfg1.nodes
    assert END_NODE not in dfg1.nodes

    merged = discovery.merge_dfgs([dfg1, dfg2])
    assert merged.trace_count == 2
    edge = merged.edges[("ACCESO_CURSO", "CONSULTA_RECURSO")]
    assert edge.freq == 2
    assert edge.total_time_sec == pytest.approx(90.0)
    assert edge.trace_support_count == 2


def test_engine_both_arrival_orders_produce_identical_additive_cluster_dfg() -> None:
    cfg = ProcessMiningConfig(algorithm="dfg", include_boundaries=True, min_edge_frequency=1)

    t1 = _trace_msg(
        "u1",
        [
            _item("1", "ACCESO_CURSO", 0),
            _item("2", "CONSULTA_RECURSO", 20),
            _item("3", "ENVIO_TAREA", 80),
        ],
    )
    t2 = _trace_msg(
        "u2",
        [
            _item("4", "ACCESO_CURSO", 0),
            _item("5", "CONSULTA_RECURSO", 40),
            _item("6", "CONSULTA_RECURSO", 70),
        ],
    )
    a1 = _assign_msg("u1", 0)
    a2 = _assign_msg("u2", 0)

    now = datetime(2026, 11, 24, 12, 0, 5, tzinfo=UTC)

    # Orden A: trazas antes de asignaciones
    eng_a = ProcessMiningEngine(cfg)
    r_t1 = eng_a.process_trace(t1, processed_at=now)
    assert r_t1.student_graph is not None
    assert r_t1.cluster_graphs == []
    eng_a.process_trace(t2, processed_at=now)
    eng_a.process_assignment(a1, processed_at=now)
    r_a2 = eng_a.process_assignment(a2, processed_at=now)
    cluster_a = r_a2.cluster_graphs[0]

    # Orden B: asignaciones antes de trazas
    eng_b = ProcessMiningEngine(cfg)
    p1 = eng_b.process_assignment(a1, processed_at=now)
    assert p1.pending is True
    p2 = eng_b.process_assignment(a2, processed_at=now)
    assert p2.pending is True
    eng_b.process_trace(t1, processed_at=now)
    r_b2 = eng_b.process_trace(t2, processed_at=now)
    cluster_b = r_b2.cluster_graphs[0]

    edges_a = {
        (e.source, e.target): (e.freq, e.total_time_sec, e.mean_time_sec, e.support)
        for e in cluster_a.edges
    }
    edges_b = {
        (e.source, e.target): (e.freq, e.total_time_sec, e.mean_time_sec, e.support)
        for e in cluster_b.edges
    }
    assert edges_a == edges_b
    assert cluster_a.trace_count == 2
    assert edges_a[("ACCESO_CURSO", "CONSULTA_RECURSO")] == (2, 60.0, 30.0, 1.0)
    assert edges_a[("CONSULTA_RECURSO", "CONSULTA_RECURSO")] == (1, 30.0, 30.0, 0.5)
    assert edges_a[("CONSULTA_RECURSO", "ENVIO_TAREA")] == (1, 60.0, 60.0, 0.5)


def test_engine_idempotency_reassignment_and_granularity_isolation() -> None:
    cfg = ProcessMiningConfig(algorithm="dfg", include_boundaries=True, min_edge_frequency=1)
    engine = ProcessMiningEngine(cfg)
    now = datetime(2026, 11, 24, 12, 0, 5, tzinfo=UTC)

    t1 = _trace_msg("u1", [_item("1", "ACCESO_CURSO", 0), _item("2", "ENVIO_TAREA", 50)])
    t1_daily = _trace_msg(
        "u1",
        [_item("3", "ACCESO_CURSO", 0), _item("4", "PARTICIPACION_FORO", 25)],
        granularity="daily",
        window_id="2024-09-02",
    )
    a1 = _assign_msg("u1", 1)
    a1_daily = _assign_msg("u1", 1, granularity="daily", window_id="2024-09-02")

    engine.process_trace(t1, processed_at=now)
    engine.process_trace(t1_daily, processed_at=now)
    first_assign = engine.process_assignment(a1, processed_at=now)
    assert len(first_assign.cluster_graphs) == 1
    engine.process_assignment(a1_daily, processed_at=now)

    # Duplicado exacto es idempotente (no-op)
    dup_assign = engine.process_assignment(a1, processed_at=now)
    assert dup_assign.cluster_graphs == []
    assert dup_assign.empty_cluster_keys == []

    # Reasignar u1 del clúster 1 al clúster 2 vacía el clúster 1 y crea el 2
    reassign = engine.process_assignment(_assign_msg("u1", 2), processed_at=now)
    assert ("r1", "weekly", "2024-W36", "1") in reassign.empty_cluster_keys
    assert len(reassign.cluster_graphs) == 1
    assert reassign.cluster_graphs[0].scope_id == "2"
    assert reassign.cluster_graphs[0].trace_count == 1


def test_unknown_process_discovery_algorithm_fails_fast() -> None:
    bad_cfg = ProcessMiningConfig(algorithm="heuristic_unknown")
    with pytest.raises(ValueError, match="no soportado"):
        create_process_discovery(bad_cfg)
