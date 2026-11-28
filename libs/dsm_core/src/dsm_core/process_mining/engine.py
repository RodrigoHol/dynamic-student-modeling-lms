from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from dsm_common.config import ProcessMiningConfig
from dsm_common.schemas import ClusterAssignmentMessage, DfgGraphDocument, TraceMessage
from dsm_common.time import ensure_utc, utc_now
from dsm_core.process_mining.models import (
    DfgData,
    add_dfg_in_place,
    dfg_data_to_document,
    subtract_dfg_in_place,
)
from dsm_core.process_mining.registry import create_process_discovery

StudentWindowKey = tuple[str, str, str, str]  # (run_id, granularity, window_id, student_id)
ClusterWindowKey = tuple[str, str, str, str]  # (run_id, granularity, window_id, cluster_id)


@dataclass(slots=True)
class ProcessMiningUpdateResult:
    student_graph: DfgGraphDocument | None = None
    cluster_graphs: list[DfgGraphDocument] = field(default_factory=list)
    empty_cluster_keys: list[ClusterWindowKey] = field(default_factory=list)
    pending: bool = False


@dataclass(slots=True)
class _StudentWindowState:
    trace_msg: TraceMessage
    dfg: DfgData
    applied_cluster_id: str | None = None


@dataclass(slots=True)
class _ClusterWindowState:
    course_id: str
    window_start: datetime
    window_end: datetime
    dfg: DfgData
    last_event_ingested_at: datetime


class ProcessMiningEngine:
    """Motor puro de minería de procesos concurrente con DFG aditivo (ADR-10, ADR-13)."""

    def __init__(self, config: ProcessMiningConfig) -> None:
        self._config = config
        self._algorithm_name = config.algorithm.strip().lower()
        self._discovery = create_process_discovery(config)
        self._students: dict[StudentWindowKey, _StudentWindowState] = {}
        self._clusters: dict[ClusterWindowKey, _ClusterWindowState] = {}
        self._pending_assignments: dict[StudentWindowKey, ClusterAssignmentMessage] = {}

    @property
    def algorithm_name(self) -> str:
        return self._algorithm_name

    @staticmethod
    def _latency_ms(now: datetime, ingested_at: datetime) -> int:
        return max(0, int((now - ingested_at).total_seconds() * 1000))

    def _build_cluster_doc(
        self,
        key: ClusterWindowKey,
        state: _ClusterWindowState,
        *,
        now: datetime,
    ) -> DfgGraphDocument:
        run_id, granularity, window_id, cluster_id = key
        return dfg_data_to_document(
            state.dfg,
            run_id=run_id,
            course_id=state.course_id,
            granularity=granularity,
            window_id=window_id,
            window_start=state.window_start,
            window_end=state.window_end,
            scope="cluster",
            scope_id=cluster_id,
            algorithm=self._algorithm_name,
            min_edge_frequency=self._config.min_edge_frequency,
            ingested_to_graph_ms=self._latency_ms(now, state.last_event_ingested_at),
            updated_at=now,
        )

    def _add_to_cluster(
        self,
        *,
        run_id: str,
        course_id: str,
        granularity: str,
        window_id: str,
        window_start: datetime,
        window_end: datetime,
        cluster_id: str,
        student_dfg: DfgData,
        ingested_at: datetime,
        now: datetime,
    ) -> DfgGraphDocument:
        ckey: ClusterWindowKey = (run_id, granularity, window_id, cluster_id)
        cluster_state = self._clusters.get(ckey)
        if cluster_state is None:
            cluster_state = _ClusterWindowState(
                course_id=course_id,
                window_start=window_start,
                window_end=window_end,
                dfg=DfgData(include_boundaries=self._config.include_boundaries),
                last_event_ingested_at=ingested_at,
            )
            self._clusters[ckey] = cluster_state
        elif ingested_at > cluster_state.last_event_ingested_at:
            cluster_state.last_event_ingested_at = ingested_at

        add_dfg_in_place(cluster_state.dfg, student_dfg)
        return self._build_cluster_doc(ckey, cluster_state, now=now)

    def _remove_from_cluster(
        self,
        *,
        run_id: str,
        granularity: str,
        window_id: str,
        cluster_id: str,
        student_dfg: DfgData,
        now: datetime,
    ) -> tuple[DfgGraphDocument | None, ClusterWindowKey | None]:
        ckey: ClusterWindowKey = (run_id, granularity, window_id, cluster_id)
        cluster_state = self._clusters.get(ckey)
        if cluster_state is None:
            return None, None
        subtract_dfg_in_place(cluster_state.dfg, student_dfg)
        if cluster_state.dfg.trace_count == 0:
            del self._clusters[ckey]
            return None, ckey
        return self._build_cluster_doc(ckey, cluster_state, now=now), None

    def process_trace(
        self,
        msg: TraceMessage,
        *,
        processed_at: datetime | None = None,
    ) -> ProcessMiningUpdateResult:
        now = ensure_utc(processed_at) if processed_at is not None else utc_now()
        student_dfg = self._discovery.build_student_dfg(msg.trace)
        student_doc = dfg_data_to_document(
            student_dfg,
            run_id=msg.run_id,
            course_id=msg.course_id,
            granularity=msg.granularity,
            window_id=msg.window_id,
            window_start=msg.window_start,
            window_end=msg.window_end,
            scope="student",
            scope_id=msg.u,
            algorithm=self._algorithm_name,
            min_edge_frequency=1,
            ingested_to_graph_ms=self._latency_ms(now, msg.last_event_ingested_at),
            updated_at=now,
        )

        skey: StudentWindowKey = (msg.run_id, msg.granularity, msg.window_id, msg.u)
        prev_state = self._students.get(skey)
        pending_assign = self._pending_assignments.pop(skey, None)

        cluster_graphs: list[DfgGraphDocument] = []
        empty_cluster_keys: list[ClusterWindowKey] = []

        if prev_state is not None and prev_state.applied_cluster_id is not None:
            target_cid = (
                str(pending_assign.cluster_id)
                if pending_assign is not None
                else prev_state.applied_cluster_id
            )
            if target_cid == prev_state.applied_cluster_id:
                updated_doc, empty_key = self._remove_from_cluster(
                    run_id=msg.run_id,
                    granularity=msg.granularity,
                    window_id=msg.window_id,
                    cluster_id=prev_state.applied_cluster_id,
                    student_dfg=prev_state.dfg,
                    now=now,
                )
                if empty_key is not None:
                    empty_cluster_keys.append(empty_key)
                _ = updated_doc
                ingested_at = (
                    max(msg.last_event_ingested_at, pending_assign.last_event_ingested_at)
                    if pending_assign is not None
                    else msg.last_event_ingested_at
                )
                cluster_graphs.append(
                    self._add_to_cluster(
                        run_id=msg.run_id,
                        course_id=msg.course_id,
                        granularity=msg.granularity,
                        window_id=msg.window_id,
                        window_start=msg.window_start,
                        window_end=msg.window_end,
                        cluster_id=target_cid,
                        student_dfg=student_dfg,
                        ingested_at=ingested_at,
                        now=now,
                    )
                )
            else:
                updated_old, empty_key = self._remove_from_cluster(
                    run_id=msg.run_id,
                    granularity=msg.granularity,
                    window_id=msg.window_id,
                    cluster_id=prev_state.applied_cluster_id,
                    student_dfg=prev_state.dfg,
                    now=now,
                )
                if updated_old is not None:
                    cluster_graphs.append(updated_old)
                if empty_key is not None:
                    empty_cluster_keys.append(empty_key)
                cluster_graphs.append(
                    self._add_to_cluster(
                        run_id=msg.run_id,
                        course_id=msg.course_id,
                        granularity=msg.granularity,
                        window_id=msg.window_id,
                        window_start=msg.window_start,
                        window_end=msg.window_end,
                        cluster_id=target_cid,
                        student_dfg=student_dfg,
                        ingested_at=max(
                            msg.last_event_ingested_at,
                            pending_assign.last_event_ingested_at,  # type: ignore[union-attr]
                        ),
                        now=now,
                    )
                )
            applied_cid: str | None = target_cid
        elif pending_assign is not None:
            applied_cid = str(pending_assign.cluster_id)
            cluster_graphs.append(
                self._add_to_cluster(
                    run_id=msg.run_id,
                    course_id=msg.course_id,
                    granularity=msg.granularity,
                    window_id=msg.window_id,
                    window_start=msg.window_start,
                    window_end=msg.window_end,
                    cluster_id=applied_cid,
                    student_dfg=student_dfg,
                    ingested_at=max(
                        msg.last_event_ingested_at,
                        pending_assign.last_event_ingested_at,
                    ),
                    now=now,
                )
            )
        else:
            applied_cid = None

        self._students[skey] = _StudentWindowState(
            trace_msg=msg,
            dfg=student_dfg,
            applied_cluster_id=applied_cid,
        )

        return ProcessMiningUpdateResult(
            student_graph=student_doc,
            cluster_graphs=cluster_graphs,
            empty_cluster_keys=empty_cluster_keys,
            pending=False,
        )

    def process_assignment(
        self,
        msg: ClusterAssignmentMessage,
        *,
        processed_at: datetime | None = None,
    ) -> ProcessMiningUpdateResult:
        now = ensure_utc(processed_at) if processed_at is not None else utc_now()
        skey: StudentWindowKey = (msg.run_id, msg.granularity, msg.window_id, msg.u)
        target_cid = str(msg.cluster_id)

        student_state = self._students.get(skey)
        if student_state is None:
            self._pending_assignments[skey] = msg
            return ProcessMiningUpdateResult(pending=True)

        if student_state.applied_cluster_id == target_cid:
            return ProcessMiningUpdateResult(pending=False)

        cluster_graphs: list[DfgGraphDocument] = []
        empty_cluster_keys: list[ClusterWindowKey] = []

        if student_state.applied_cluster_id is not None:
            updated_old, empty_key = self._remove_from_cluster(
                run_id=msg.run_id,
                granularity=msg.granularity,
                window_id=msg.window_id,
                cluster_id=student_state.applied_cluster_id,
                student_dfg=student_state.dfg,
                now=now,
            )
            if updated_old is not None:
                cluster_graphs.append(updated_old)
            if empty_key is not None:
                empty_cluster_keys.append(empty_key)

        ingested_at = max(
            student_state.trace_msg.last_event_ingested_at,
            msg.last_event_ingested_at,
        )
        cluster_graphs.append(
            self._add_to_cluster(
                run_id=msg.run_id,
                course_id=student_state.trace_msg.course_id,
                granularity=msg.granularity,
                window_id=msg.window_id,
                window_start=student_state.trace_msg.window_start,
                window_end=student_state.trace_msg.window_end,
                cluster_id=target_cid,
                student_dfg=student_state.dfg,
                ingested_at=ingested_at,
                now=now,
            )
        )
        student_state.applied_cluster_id = target_cid

        return ProcessMiningUpdateResult(
            student_graph=None,
            cluster_graphs=cluster_graphs,
            empty_cluster_keys=empty_cluster_keys,
            pending=False,
        )
