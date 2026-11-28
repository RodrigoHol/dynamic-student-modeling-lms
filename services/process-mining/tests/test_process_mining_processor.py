from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from dsm_common.config import load_process_mining_config
from dsm_common.messaging import InMemoryEventProducer, Topics
from dsm_common.schemas import ClusterAssignmentMessage, TraceEventItem, TraceMessage
from dsm_common.storage import InMemoryGraphRepository
from dsm_core.process_mining import ProcessMiningEngine
from dsm_process_mining.config import ProcessMiningServiceSettings
from dsm_process_mining.processor import ProcessMiningServiceProcessor

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_trace_payload(u: str, hles: list[str], *, window_id: str = "2024-W36") -> dict:
    base = datetime(2024, 9, 2, 10, 0, tzinfo=UTC)
    now = datetime.now(UTC)
    items = [
        TraceEventItem(
            event_id=f"{u}_{idx}",
            hle=hle,
            t=base + timedelta(seconds=idx * 20),
            a="viewed",
            resource_id=f"res_{idx}",
            resource_type="resource",
        )
        for idx, hle in enumerate(hles)
    ]
    msg = TraceMessage(
        run_id="run_pm_1",
        course_id="course_105",
        u=u,
        granularity="weekly",
        window_id=window_id,
        window_start=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 9, 9, 0, 0, tzinfo=UTC),
        hle_version="v0.1-provisional",
        trace=items,
        event_count=len(items),
        last_event_ingested_at=now - timedelta(milliseconds=20),
        emitted_at=now,
    )
    return msg.model_dump(mode="json")


def _make_assignment_payload(u: str, cluster_id: int, *, window_id: str = "2024-W36") -> dict:
    now = datetime.now(UTC)
    msg = ClusterAssignmentMessage(
        run_id="run_pm_1",
        course_id="course_105",
        u=u,
        granularity="weekly",
        window_id=window_id,
        window_start=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 9, 9, 0, 0, tzinfo=UTC),
        algorithm="denstream",
        cluster_id=cluster_id,
        last_event_ingested_at=now - timedelta(milliseconds=10),
        emitted_at=now,
    )
    return msg.model_dump(mode="json")


async def test_process_mining_service_persists_student_and_additive_cluster_dfgs() -> None:
    cfg = load_process_mining_config(REPO_ROOT / "config" / "process_mining.yaml")
    engine = ProcessMiningEngine(cfg)
    repo = InMemoryGraphRepository()
    producer = InMemoryEventProducer()
    await producer.start()

    processor = ProcessMiningServiceProcessor(engine, repo, producer)

    # Orden 1: traza -> asignación para usr_1
    r1 = await processor.handle_topic_payload(
        Topics.TRACES,
        _make_trace_payload("usr_1", ["ACCESO_CURSO", "CONSULTA_RECURSO"]),
    )
    assert r1 is not None and r1.student_graph is not None

    r2 = await processor.handle_topic_payload(
        Topics.ASSIGNMENTS,
        _make_assignment_payload("usr_1", 0),
    )
    assert r2 is not None and len(r2.cluster_graphs) == 1

    # Orden 2: asignación -> traza para usr_2 en el mismo clúster 0
    r3 = await processor.handle_topic_payload(
        Topics.ASSIGNMENTS,
        _make_assignment_payload("usr_2", 0),
    )
    assert r3 is not None and r3.pending is True

    r4 = await processor.handle_topic_payload(
        Topics.TRACES,
        _make_trace_payload("usr_2", ["ACCESO_CURSO", "CONSULTA_RECURSO", "ENVIO_TAREA"]),
    )
    assert r4 is not None and r4.student_graph is not None and len(r4.cluster_graphs) == 1

    cluster_edges = await repo.fetch_dfg(
        run_id="run_pm_1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    by_pair = {(e["source"], e["target"]): e for e in cluster_edges}
    assert by_pair[("ACCESO_CURSO", "CONSULTA_RECURSO")]["freq"] == 2
    assert by_pair[("ACCESO_CURSO", "CONSULTA_RECURSO")]["total_time_sec"] == 40.0
    assert by_pair[("ACCESO_CURSO", "CONSULTA_RECURSO")]["mean_time_sec"] == 20.0
    assert by_pair[("CONSULTA_RECURSO", "ENVIO_TAREA")]["freq"] == 1
    assert by_pair[("CONSULTA_RECURSO", "ENVIO_TAREA")]["support"] == 0.5

    # Payloads inválidos se enrutan a DLQ sin detener el procesador
    bad_trace = await processor.handle_topic_payload(Topics.TRACES, {"bad": "trace"})
    bad_assign = await processor.handle_topic_payload(Topics.ASSIGNMENTS, "not-a-dict")
    assert bad_trace is None
    assert bad_assign is None
    dlq_msgs = [m for m in producer.messages if m.topic == Topics.DLQ_EVENTS]
    assert len(dlq_msgs) == 2

    settings = ProcessMiningServiceSettings()
    assert settings.process_mining_metrics_port == 8006
    await producer.stop()


async def test_process_batch_coalesces_cluster_writes() -> None:
    class _CountingRepo(InMemoryGraphRepository):
        def __init__(self) -> None:
            super().__init__()
            self.upsert_calls = 0

        async def upsert_dfg(self, graph):  # type: ignore[override]
            self.upsert_calls += 1
            await super().upsert_dfg(graph)

    cfg = load_process_mining_config(REPO_ROOT / "config" / "process_mining.yaml")
    engine = ProcessMiningEngine(cfg)
    repo = _CountingRepo()
    producer = InMemoryEventProducer()
    await producer.start()

    processor = ProcessMiningServiceProcessor(engine, repo, producer)
    written = await processor.process_batch(
        [
            _make_trace_payload("usr_a", ["ACCESO_CURSO", "CONSULTA_RECURSO"]),
            _make_trace_payload("usr_b", ["ACCESO_CURSO", "ENVIO_TAREA"]),
        ],
        [
            _make_assignment_payload("usr_a", 0),
            _make_assignment_payload("usr_b", 0),
        ],
    )
    # 2 student graphs + 1 coalesced cluster graph (en vez de 2 escrituras de clúster)
    assert written == 3
    assert repo.upsert_calls == 3
    cluster_edges = await repo.fetch_dfg(
        run_id="run_pm_1",
        granularity="weekly",
        window_id="2024-W36",
        scope="cluster",
        scope_id="0",
    )
    assert cluster_edges[0]["trace_count"] == 2
    await producer.stop()
