from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from dsm_common.config import FeaturesConfig, HleCatalogConfig, WindowsConfig
from dsm_common.schemas import (
    CanonicalEvent,
    FeatureVectorMessage,
    TraceEventItem,
    TraceMessage,
)
from dsm_common.time import utc_now
from dsm_core.features import FeaturePipeline, WindowContext
from dsm_core.preprocessing import HLEMapper, NoiseFilter, extract_match_context
from dsm_core.windowing import (
    ClosedWindow,
    KeyValueState,
    MultiGranularityWindowManager,
    WindowAssignmentOutcome,
)

EventStatus = Literal["mapped", "noise", "duplicate"]


def window_partition_key(granularity: str, u: str) -> str:
    return f"{granularity}:{u}"


def build_window_outputs(
    closed_window: ClosedWindow,
    feature_pipeline: FeaturePipeline,
    *,
    hle_version: str,
    emitted_at: datetime | None = None,
) -> tuple[FeatureVectorMessage, TraceMessage]:
    now = emitted_at or utc_now()
    context = WindowContext(
        window_start=closed_window.window_start,
        window_end=closed_window.window_end,
        hle_categories=feature_pipeline.hle_categories,
    )
    features = feature_pipeline.extract(closed_window.events, context)

    feature_msg = FeatureVectorMessage(
        run_id=closed_window.run_id,
        course_id=closed_window.course_id,
        u=closed_window.u,
        granularity=closed_window.granularity,
        window_id=closed_window.window_id,
        window_start=closed_window.window_start,
        window_end=closed_window.window_end,
        features_version=feature_pipeline.version,
        hle_version=hle_version,
        features=features,
        event_count=len(closed_window.events),
        last_event_ingested_at=closed_window.last_event_ingested_at,
        emitted_at=now,
    )

    trace_items = [
        TraceEventItem(
            event_id=ev.event_id,
            hle=ev.M.hle or "OTRO",
            t=ev.t,
            a=ev.a,
            resource_id=ev.r.resource_id,
            resource_type=ev.r.resource_type,
            session_hash=ev.M.session_hash,
        )
        for ev in closed_window.events
    ]
    trace_msg = TraceMessage(
        run_id=closed_window.run_id,
        course_id=closed_window.course_id,
        u=closed_window.u,
        granularity=closed_window.granularity,
        window_id=closed_window.window_id,
        window_start=closed_window.window_start,
        window_end=closed_window.window_end,
        hle_version=hle_version,
        trace=trace_items,
        event_count=len(trace_items),
        last_event_ingested_at=closed_window.last_event_ingested_at,
        emitted_at=now,
    )
    return feature_msg, trace_msg


@dataclass(slots=True)
class ProcessEventResult:
    status: EventStatus
    enriched_event: CanonicalEvent | None = None
    outputs: list[tuple[FeatureVectorMessage, TraceMessage]] = field(default_factory=list)
    dropped_late_granularities: list[str] = field(default_factory=list)


class PreprocessingEngine:
    def __init__(
        self,
        hle_catalog: HleCatalogConfig,
        features_config: FeaturesConfig,
        windows_config: WindowsConfig,
        *,
        course_start: datetime | None = None,
        course_end: datetime | None = None,
    ) -> None:
        self.noise_filter = NoiseFilter(hle_catalog)
        self.hle_mapper = HLEMapper(hle_catalog)
        self.feature_pipeline = FeaturePipeline(
            features_config,
            hle_categories=self.hle_mapper.known_hles,
        )
        self.window_manager = MultiGranularityWindowManager(
            windows_config,
            course_start=course_start,
            course_end=course_end,
        )
        self._windows_config = windows_config
        self._course_start = course_start
        self._course_end = course_end

    def _build_outputs(
        self,
        closed_windows: list[ClosedWindow],
        emitted_at: datetime | None,
    ) -> list[tuple[FeatureVectorMessage, TraceMessage]]:
        now = emitted_at or utc_now()
        return [
            build_window_outputs(
                cw,
                self.feature_pipeline,
                hle_version=self.hle_mapper.version,
                emitted_at=now,
            )
            for cw in closed_windows
        ]

    def _to_result(
        self,
        enriched: CanonicalEvent,
        outcome: WindowAssignmentOutcome,
        emitted_at: datetime | None,
    ) -> ProcessEventResult:
        if outcome.is_duplicate:
            return ProcessEventResult(
                status="duplicate",
                enriched_event=enriched,
                dropped_late_granularities=outcome.dropped_late_granularities,
            )
        return ProcessEventResult(
            status="mapped",
            enriched_event=enriched,
            outputs=self._build_outputs(outcome.closed_windows, emitted_at),
            dropped_late_granularities=outcome.dropped_late_granularities,
        )

    def _enrich_or_filter(self, event: CanonicalEvent) -> CanonicalEvent | None:
        context = extract_match_context(event)
        if self.noise_filter.matches_context(context):
            return None
        hle = self.hle_mapper.map_context(context)
        return self.hle_mapper.with_hle(event, hle)

    def process_event(
        self,
        event: CanonicalEvent,
        *,
        emitted_at: datetime | None = None,
    ) -> ProcessEventResult:
        enriched = self._enrich_or_filter(event)
        if enriched is None:
            return ProcessEventResult(status="noise")
        outcome = self.window_manager.ingest(enriched)
        return self._to_result(enriched, outcome, emitted_at)

    def process_event_with_state(
        self,
        event: CanonicalEvent,
        state: KeyValueState,
        *,
        state_key: str = "window_state",
        emitted_at: datetime | None = None,
    ) -> ProcessEventResult:
        enriched = self._enrich_or_filter(event)
        if enriched is None:
            return ProcessEventResult(status="noise")
        outcome = self.window_manager.ingest_with_state(enriched, state, state_key=state_key)
        return self._to_result(enriched, outcome, emitted_at)

    def flush_run(
        self,
        run_id: str,
        *,
        u: str | None = None,
        emitted_at: datetime | None = None,
    ) -> list[tuple[FeatureVectorMessage, TraceMessage]]:
        closed_windows = self.window_manager.flush_run(run_id, u=u)
        return self._build_outputs(closed_windows, emitted_at)

    def flush_run_with_state(
        self,
        run_id: str,
        state: KeyValueState,
        *,
        u: str | None = None,
        state_key: str = "window_state",
        emitted_at: datetime | None = None,
    ) -> list[tuple[FeatureVectorMessage, TraceMessage]]:
        closed_windows = self.window_manager.flush_run_with_state(
            run_id, state, u=u, state_key=state_key
        )
        return self._build_outputs(closed_windows, emitted_at)

    def export_state(self) -> dict[str, Any]:
        return self.window_manager.to_state_dict()

    def load_state(self, state_dict: dict[str, Any] | None) -> None:
        self.window_manager = MultiGranularityWindowManager.from_state_dict(
            state_dict,
            self._windows_config,
            course_start=self._course_start,
            course_end=self._course_end,
        )
