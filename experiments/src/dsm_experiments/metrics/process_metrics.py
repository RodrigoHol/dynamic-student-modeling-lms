from __future__ import annotations

from collections.abc import Sequence

import pm4py
from pm4py.objects.log.obj import Event, EventLog, Trace

from dsm_common.schemas import TraceEventItem


def build_pm4py_event_log(traces: Sequence[Sequence[TraceEventItem]]) -> EventLog:
    pm4py_traces: list[Trace] = []
    for trace_items in traces:
        if not trace_items:
            continue
        ordered = sorted(trace_items, key=lambda item: (item.t, item.event_id))
        pm4py_traces.append(
            Trace(
                [
                    Event({"concept:name": item.hle, "time:timestamp": item.t})
                    for item in ordered
                ]
            )
        )
    return EventLog(pm4py_traces)


def compute_pm_fitness_and_precision(
    traces: Sequence[Sequence[TraceEventItem]],
) -> tuple[float | None, float | None]:
    log = build_pm4py_event_log(traces)
    if len(log) == 0:
        return None, None

    net, im, fm = pm4py.discover_petri_net_inductive(log)
    fit_res = pm4py.fitness_token_based_replay(log, net, im, fm)
    fitness = float(
        fit_res.get("log_fitness", fit_res.get("average_trace_fitness", 0.0))
    )
    precision = float(pm4py.precision_token_based_replay(log, net, im, fm))
    return (
        round(min(1.0, max(0.0, fitness)), 6),
        round(min(1.0, max(0.0, precision)), 6),
    )
