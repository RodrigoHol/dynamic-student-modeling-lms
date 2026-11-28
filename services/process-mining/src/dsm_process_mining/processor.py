from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from dsm_common.messaging import EventProducer, Topics
from dsm_common.schemas import (
    ClusterAssignmentMessage,
    DfgGraphDocument,
    TraceMessage,
    make_dlq_event,
)
from dsm_common.storage import GraphRepository
from dsm_core.process_mining import (
    ClusterWindowKey,
    ProcessMiningEngine,
    ProcessMiningUpdateResult,
)
from dsm_process_mining.metrics import (
    PM_ASSIGNMENTS_TOTAL,
    PM_GRAPHS_PERSISTED_TOTAL,
    PM_INGESTED_TO_GRAPH_LATENCY_SECONDS,
    PM_PROCESSING_LATENCY_SECONDS,
    PM_TRACES_TOTAL,
)

GraphKey = tuple[str, str, str, str, str]  # (run_id, granularity, window_id, scope, scope_id)


def _graph_key(doc: DfgGraphDocument) -> GraphKey:
    return (doc.run_id, doc.granularity, doc.window_id, doc.scope, doc.scope_id)


def _cluster_graph_key(key: ClusterWindowKey) -> GraphKey:
    run_id, granularity, window_id, cluster_id = key
    return (run_id, granularity, window_id, "cluster", cluster_id)


class ProcessMiningServiceProcessor:
    """Orquesta consumo de trazas/asignaciones y persistencia incremental de DFG en Neo4j."""

    def __init__(
        self,
        engine: ProcessMiningEngine,
        repository: GraphRepository,
        producer: EventProducer,
    ) -> None:
        self._engine = engine
        self._repository = repository
        self._producer = producer

    async def _send_to_dlq(
        self,
        raw_payload: Any,
        reason: str,
        *,
        kind: str,
        granularity: str = "unknown",
    ) -> None:
        if kind == "trace":
            PM_TRACES_TOTAL.labels(status="invalid", granularity=granularity).inc()
        else:
            PM_ASSIGNMENTS_TOTAL.labels(status="invalid", granularity=granularity).inc()
        dlq = make_dlq_event(raw_payload, reason)
        await self._producer.publish(
            Topics.DLQ_EVENTS,
            key=dlq.dlq_id,
            value=dlq.model_dump(mode="json"),
        )

    def _collect_result(
        self,
        result: ProcessMiningUpdateResult,
        pending_upserts: dict[GraphKey, DfgGraphDocument],
        pending_deletes: set[GraphKey],
    ) -> None:
        if result.student_graph is not None:
            gkey = _graph_key(result.student_graph)
            pending_deletes.discard(gkey)
            pending_upserts[gkey] = result.student_graph

        for cgraph in result.cluster_graphs:
            gkey = _graph_key(cgraph)
            pending_deletes.discard(gkey)
            pending_upserts[gkey] = cgraph

        for empty_key in result.empty_cluster_keys:
            gkey = _cluster_graph_key(empty_key)
            pending_upserts.pop(gkey, None)
            pending_deletes.add(gkey)

    async def _flush_writes(
        self,
        pending_upserts: dict[GraphKey, DfgGraphDocument],
        pending_deletes: set[GraphKey],
    ) -> None:
        for graph in pending_upserts.values():
            await self._repository.upsert_dfg(graph)
            PM_GRAPHS_PERSISTED_TOTAL.labels(
                scope=graph.scope,
                granularity=graph.granularity,
            ).inc()
            PM_INGESTED_TO_GRAPH_LATENCY_SECONDS.labels(scope=graph.scope).observe(
                graph.ingested_to_graph_ms / 1000.0
            )

        for run_id, granularity, window_id, scope, scope_id in pending_deletes:
            await self._repository.delete_dfg(
                run_id=run_id,
                granularity=granularity,
                window_id=window_id,
                scope=scope,
                scope_id=scope_id,
            )

    async def _apply_trace(
        self,
        raw_payload: Any,
        pending_upserts: dict[GraphKey, DfgGraphDocument],
        pending_deletes: set[GraphKey],
    ) -> ProcessMiningUpdateResult | None:
        started = perf_counter()
        try:
            if not isinstance(raw_payload, dict):
                await self._send_to_dlq(
                    raw_payload,
                    "El mensaje en analytics.traces debe ser un objeto JSON.",
                    kind="trace",
                )
                return None

            granularity_hint = str(raw_payload.get("granularity") or "unknown")
            try:
                msg = TraceMessage.model_validate(raw_payload)
            except ValidationError as exc:
                await self._send_to_dlq(
                    raw_payload,
                    f"TraceMessage inválido: {exc}",
                    kind="trace",
                    granularity=granularity_hint,
                )
                return None

            result = self._engine.process_trace(msg)
            self._collect_result(result, pending_upserts, pending_deletes)
            PM_TRACES_TOTAL.labels(status="ok", granularity=msg.granularity).inc()
            return result
        finally:
            PM_PROCESSING_LATENCY_SECONDS.observe(perf_counter() - started)

    async def _apply_assignment(
        self,
        raw_payload: Any,
        pending_upserts: dict[GraphKey, DfgGraphDocument],
        pending_deletes: set[GraphKey],
    ) -> ProcessMiningUpdateResult | None:
        started = perf_counter()
        try:
            if not isinstance(raw_payload, dict):
                await self._send_to_dlq(
                    raw_payload,
                    "El mensaje en analytics.assignments debe ser un objeto JSON.",
                    kind="assignment",
                )
                return None

            granularity_hint = str(raw_payload.get("granularity") or "unknown")
            try:
                msg = ClusterAssignmentMessage.model_validate(raw_payload)
            except ValidationError as exc:
                await self._send_to_dlq(
                    raw_payload,
                    f"ClusterAssignmentMessage inválido: {exc}",
                    kind="assignment",
                    granularity=granularity_hint,
                )
                return None

            result = self._engine.process_assignment(msg)
            self._collect_result(result, pending_upserts, pending_deletes)
            status = "pending" if result.pending else "ok"
            PM_ASSIGNMENTS_TOTAL.labels(status=status, granularity=msg.granularity).inc()
            return result
        finally:
            PM_PROCESSING_LATENCY_SECONDS.observe(perf_counter() - started)

    async def process_batch(
        self,
        trace_payloads: Sequence[Any],
        assignment_payloads: Sequence[Any],
    ) -> int:
        """Procesa un lote de Kafka coalesciendo escrituras redundantes en Neo4j."""
        pending_upserts: dict[GraphKey, DfgGraphDocument] = {}
        pending_deletes: set[GraphKey] = set()

        for payload in trace_payloads:
            await self._apply_trace(payload, pending_upserts, pending_deletes)
        for payload in assignment_payloads:
            await self._apply_assignment(payload, pending_upserts, pending_deletes)

        await self._flush_writes(pending_upserts, pending_deletes)
        return len(pending_upserts) + len(pending_deletes)

    async def handle_trace_payload(self, raw_payload: Any) -> ProcessMiningUpdateResult | None:
        pending_upserts: dict[GraphKey, DfgGraphDocument] = {}
        pending_deletes: set[GraphKey] = set()
        result = await self._apply_trace(raw_payload, pending_upserts, pending_deletes)
        await self._flush_writes(pending_upserts, pending_deletes)
        return result

    async def handle_assignment_payload(
        self,
        raw_payload: Any,
    ) -> ProcessMiningUpdateResult | None:
        pending_upserts: dict[GraphKey, DfgGraphDocument] = {}
        pending_deletes: set[GraphKey] = set()
        result = await self._apply_assignment(raw_payload, pending_upserts, pending_deletes)
        await self._flush_writes(pending_upserts, pending_deletes)
        return result

    async def handle_topic_payload(
        self,
        topic: str,
        raw_payload: Any,
    ) -> ProcessMiningUpdateResult | None:
        if topic == Topics.TRACES:
            return await self.handle_trace_payload(raw_payload)
        if topic == Topics.ASSIGNMENTS:
            return await self.handle_assignment_payload(raw_payload)
        raise ValueError(f"Topic no soportado por C6 Process Mining Engine: {topic}")
