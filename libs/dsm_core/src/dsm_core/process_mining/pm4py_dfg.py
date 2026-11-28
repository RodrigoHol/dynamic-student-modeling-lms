from __future__ import annotations

from collections.abc import Sequence

import pm4py
from pm4py.objects.log.obj import Event, EventLog, Trace

from dsm_common.schemas import TraceEventItem
from dsm_core.process_mining.base import ProcessDiscovery
from dsm_core.process_mining.models import (
    END_NODE,
    START_NODE,
    DfgData,
    EdgeStats,
    add_dfg_in_place,
)


class PM4PyDFGDiscovery(ProcessDiscovery):
    """Descubre grafos DFG individuales con PM4Py y los fusiona aditivamente (ADR-08, ADR-13)."""

    name = "dfg"

    def __init__(self, *, include_boundaries: bool = True) -> None:
        self.include_boundaries = include_boundaries

    def build_student_dfg(self, trace: Sequence[TraceEventItem]) -> DfgData:
        if not trace:
            return DfgData(include_boundaries=self.include_boundaries)

        ordered = sorted(trace, key=lambda item: (item.t, item.event_id))
        pm4py_trace = Trace(
            [
                Event({"concept:name": item.hle, "time:timestamp": item.t})
                for item in ordered
            ]
        )
        log = EventLog([pm4py_trace])

        dfg_counts, start_activities, end_activities = pm4py.discover_dfg(log)
        perf_stats, _, _ = pm4py.discover_performance_dfg(log)

        nodes: set[str] = {item.hle for item in ordered}
        edges: dict[tuple[str, str], EdgeStats] = {}

        for (src, dst), freq in dfg_counts.items():
            edge_perf = perf_stats.get((src, dst))
            if isinstance(edge_perf, dict):
                total_time_sec = float(edge_perf.get("sum", 0.0))
            elif isinstance(edge_perf, (int, float)):
                total_time_sec = float(edge_perf) * int(freq)
            else:
                total_time_sec = 0.0

            edges[(src, dst)] = EdgeStats(
                freq=int(freq),
                total_time_sec=max(0.0, total_time_sec),
                trace_support_count=1,
            )

        if self.include_boundaries:
            if start_activities:
                nodes.add(START_NODE)
                for act, freq in start_activities.items():
                    edges[(START_NODE, act)] = EdgeStats(
                        freq=int(freq),
                        total_time_sec=0.0,
                        trace_support_count=1,
                    )
            if end_activities:
                nodes.add(END_NODE)
                for act, freq in end_activities.items():
                    edges[(act, END_NODE)] = EdgeStats(
                        freq=int(freq),
                        total_time_sec=0.0,
                        trace_support_count=1,
                    )

        return DfgData(
            nodes=nodes,
            node_counts=dict.fromkeys(nodes, 1),
            edges=edges,
            trace_count=1,
            include_boundaries=self.include_boundaries,
        )

    def merge_dfgs(self, dfgs: Sequence[DfgData]) -> DfgData:
        merged = DfgData(include_boundaries=self.include_boundaries)
        for dfg in dfgs:
            add_dfg_in_place(merged, dfg)
        return merged
