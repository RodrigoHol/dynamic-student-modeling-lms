"""Pipeline puro de transformación semántica, ventaneo y extracción de características."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dsm_common.config import FeaturesConfig, HleCatalogConfig, WindowsConfig
from dsm_common.schemas import (
    CanonicalEvent,
    FeatureVectorMessage,
    TraceEventItem,
    TraceMessage,
)
from dsm_core.features import FeaturePipeline
from dsm_core.preprocessing import HLEMapper, NoiseFilter
from dsm_core.windowing import ClosedWindow, MultiGranularityWindowManager


def window_partition_key(granularity: str, u: str) -> str:
    """Genera la clave de partición Kafka (`granularity:u`) para topics analíticos."""
    return f"{granularity}:{u}"


def build_window_outputs(
    closed_window: ClosedWindow,
    feature_pipeline: FeaturePipeline,
    *,
    hle_version: str,
    emitted_at: datetime | None = None,
) -> tuple[FeatureVectorMessage, TraceMessage]:
    """Construye los mensajes `FeatureVectorMessage` y `TraceMessage` de una ventana cerrada."""
    now = emitted_at or datetime.now(UTC)
    window_meta = {
        "run_id": closed_window.run_id,
        "course_id": closed_window.course_id,
        "u": closed_window.u,
        "granularity": closed_window.granularity,
        "window_id": closed_window.window_id,
        "window_start": closed_window.window_start,
        "window_end": closed_window.window_end,
    }
    features = feature_pipeline.extract(closed_window.events, window_meta)

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
    """Resultado de procesar un evento canónico en `PreprocessingEngine`."""

    status: str  # "mapped" | "noise" | "duplicate"
    enriched_event: CanonicalEvent | None = None
    outputs: list[tuple[FeatureVectorMessage, TraceMessage]] = field(default_factory=list)
    dropped_late_granularities: list[str] = field(default_factory=list)


class PreprocessingEngine:
    """Orquesta filtrado de ruido, mapeo HLE, ventanas múltiples y extracción de features."""

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
        self._hle_catalog = hle_catalog
        self._features_config = features_config
        self._windows_config = windows_config
        self._course_start = course_start
        self._course_end = course_end

    def process_event(
        self,
        event: CanonicalEvent,
        *,
        emitted_at: datetime | None = None,
    ) -> ProcessEventResult:
        """Filtra, mapea HLE, asigna a ventanas y genera salidas de ventanas cerradas."""
        if self.noise_filter.is_noise(event):
            return ProcessEventResult(status="noise")

        enriched = self.hle_mapper.enrich_event(event)
        outcome = self.window_manager.ingest(enriched)

        if outcome.is_duplicate:
            return ProcessEventResult(
                status="duplicate",
                enriched_event=enriched,
                dropped_late_granularities=outcome.dropped_late_granularities,
            )

        now = emitted_at or datetime.now(UTC)
        outputs = [
            build_window_outputs(
                cw,
                self.feature_pipeline,
                hle_version=self.hle_mapper.version,
                emitted_at=now,
            )
            for cw in outcome.closed_windows
        ]
        return ProcessEventResult(
            status="mapped",
            enriched_event=enriched,
            outputs=outputs,
            dropped_late_granularities=outcome.dropped_late_granularities,
        )

    def flush_run(
        self,
        run_id: str,
        *,
        u: str | None = None,
        emitted_at: datetime | None = None,
    ) -> list[tuple[FeatureVectorMessage, TraceMessage]]:
        """Cierra las ventanas pendientes al fin de una corrida y construye sus salidas."""
        closed_windows = self.window_manager.flush_run(run_id, u=u)
        now = emitted_at or datetime.now(UTC)
        return [
            build_window_outputs(
                cw,
                self.feature_pipeline,
                hle_version=self.hle_mapper.version,
                emitted_at=now,
            )
            for cw in closed_windows
        ]

    def export_state(self) -> dict[str, Any]:
        """Exporta el estado de ventanas serializable a JSON/RocksDB."""
        return self.window_manager.to_state_dict()

    def load_state(self, state_dict: dict[str, Any] | None) -> None:
        """Restaura el estado de ventanas desde un diccionario serializado."""
        self.window_manager = MultiGranularityWindowManager.from_state_dict(
            state_dict,
            self._windows_config,
            course_start=self._course_start,
            course_end=self._course_end,
        )
