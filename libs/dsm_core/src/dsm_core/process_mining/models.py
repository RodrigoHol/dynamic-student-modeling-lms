from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from dsm_common.schemas import DfgEdge, DfgGraphDocument, DfgNode, NodeKind

START_NODE = "START"
END_NODE = "END"
BOUNDARY_NODES: frozenset[str] = frozenset({START_NODE, END_NODE})

HLE_LABELS: dict[str, str] = {
    START_NODE: "Inicio",
    END_NODE: "Fin",
    "ACCESO_CURSO": "Acceso al curso",
    "CONSULTA_RECURSO": "Consulta de recurso",
    "PARTICIPACION_FORO": "Participación en foro",
    "ENVIO_TAREA": "Envío de tarea",
    "INTENTO_CUESTIONARIO": "Intento de cuestionario",
    "REVISION_RETROALIMENTACION": "Revisión de retroalimentación",
    "OTRO": "Otra actividad",
}


def format_hle_label(code: str) -> str:
    if code in HLE_LABELS:
        return HLE_LABELS[code]
    return code.replace("_", " ").capitalize()


def node_kind(code: str) -> NodeKind:
    return "boundary" if code in BOUNDARY_NODES else "activity"


def node_category(code: str) -> str:
    return "boundary" if code in BOUNDARY_NODES else "hle"


@dataclass(slots=True)
class EdgeStats:
    freq: int
    total_time_sec: float
    trace_support_count: int


@dataclass(slots=True)
class DfgData:
    nodes: set[str] = field(default_factory=set)
    node_counts: dict[str, int] = field(default_factory=dict)
    edges: dict[tuple[str, str], EdgeStats] = field(default_factory=dict)
    trace_count: int = 0
    include_boundaries: bool = True

    def clone(self) -> DfgData:
        return DfgData(
            nodes=set(self.nodes),
            node_counts=dict(self.node_counts),
            edges={
                edge: EdgeStats(
                    freq=stats.freq,
                    total_time_sec=stats.total_time_sec,
                    trace_support_count=stats.trace_support_count,
                )
                for edge, stats in self.edges.items()
            },
            trace_count=self.trace_count,
            include_boundaries=self.include_boundaries,
        )


def add_dfg_in_place(target: DfgData, delta: DfgData) -> None:
    """Suma aditivamente frecuencias, tiempos acumulados y soporte por traza."""
    if delta.trace_count == 0 and not delta.edges:
        return

    target.trace_count += delta.trace_count
    for node in delta.nodes:
        increment = delta.node_counts.get(node, max(1, delta.trace_count))
        target.node_counts[node] = target.node_counts.get(node, 0) + increment
        target.nodes.add(node)

    for edge_key, stats in delta.edges.items():
        existing = target.edges.get(edge_key)
        if existing is None:
            target.edges[edge_key] = EdgeStats(
                freq=stats.freq,
                total_time_sec=stats.total_time_sec,
                trace_support_count=stats.trace_support_count,
            )
        else:
            existing.freq += stats.freq
            existing.total_time_sec += stats.total_time_sec
            existing.trace_support_count += stats.trace_support_count


def subtract_dfg_in_place(target: DfgData, delta: DfgData) -> None:
    """Resta la contribución de una traza individual ante reasignación o reproceso."""
    if delta.trace_count == 0 and not delta.edges:
        return

    target.trace_count = max(0, target.trace_count - delta.trace_count)
    for node in delta.nodes:
        decrement = delta.node_counts.get(node, max(1, delta.trace_count))
        remaining = target.node_counts.get(node, 0) - decrement
        if remaining <= 0:
            target.node_counts.pop(node, None)
            target.nodes.discard(node)
        else:
            target.node_counts[node] = remaining

    for edge_key, stats in delta.edges.items():
        existing = target.edges.get(edge_key)
        if existing is None:
            continue
        existing.freq -= stats.freq
        existing.total_time_sec = max(0.0, existing.total_time_sec - stats.total_time_sec)
        existing.trace_support_count -= stats.trace_support_count
        if existing.freq <= 0 or existing.trace_support_count <= 0:
            del target.edges[edge_key]

    if target.trace_count == 0:
        target.nodes.clear()
        target.node_counts.clear()
        target.edges.clear()


def _node_sort_key(code: str) -> tuple[int, str]:
    if code == START_NODE:
        return (0, code)
    if code == END_NODE:
        return (2, code)
    return (1, code)


def dfg_data_to_document(
    dfg: DfgData,
    *,
    run_id: str,
    course_id: str,
    granularity: str,
    window_id: str,
    window_start: datetime,
    window_end: datetime,
    scope: str,
    scope_id: str,
    algorithm: str,
    min_edge_frequency: int = 1,
    ingested_to_graph_ms: int = 0,
    updated_at: datetime,
) -> DfgGraphDocument:
    """Materializa un ``DfgData`` a contrato ``DfgGraphDocument`` listo para persistir."""
    edges: list[DfgEdge] = []
    for (src, dst), stats in dfg.edges.items():
        if stats.freq < min_edge_frequency or stats.freq <= 0:
            continue
        total_time = round(max(0.0, stats.total_time_sec), 6)
        mean_time = round(total_time / stats.freq, 6)
        support = (
            round(min(1.0, max(0.0, stats.trace_support_count / dfg.trace_count)), 6)
            if dfg.trace_count > 0
            else 0.0
        )
        edges.append(
            DfgEdge(
                source=src,
                target=dst,
                source_kind=node_kind(src),
                target_kind=node_kind(dst),
                freq=stats.freq,
                total_time_sec=total_time,
                mean_time_sec=mean_time,
                trace_support_count=min(stats.trace_support_count, max(1, dfg.trace_count)),
                support=support,
            )
        )

    edges.sort(key=lambda e: (-e.freq, e.source, e.target))

    if min_edge_frequency > 1 and edges:
        active_node_codes = {e.source for e in edges} | {e.target for e in edges}
    elif min_edge_frequency > 1 and dfg.edges:
        active_node_codes = set()
    else:
        active_node_codes = set(dfg.nodes)

    nodes = [
        DfgNode(
            code=code,
            label=format_hle_label(code),
            kind=node_kind(code),
            category=node_category(code),
        )
        for code in sorted(active_node_codes, key=_node_sort_key)
    ]

    return DfgGraphDocument(
        run_id=run_id,
        course_id=course_id,
        granularity=granularity,
        window_id=window_id,
        window_start=window_start,
        window_end=window_end,
        scope=scope,  # type: ignore[arg-type]
        scope_id=scope_id,
        algorithm=algorithm,
        trace_count=dfg.trace_count,
        nodes=nodes,
        edges=edges,
        ingested_to_graph_ms=ingested_to_graph_ms,
        updated_at=updated_at,
    )
