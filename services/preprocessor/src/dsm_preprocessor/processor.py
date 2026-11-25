"""Lógica stateful por estudiante para C4 Preprocessor sobre Quix Streams."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from pydantic import ValidationError

from dsm_common.config import FeaturesConfig, HleCatalogConfig, WindowsConfig
from dsm_common.observability import (
    PREPROCESSOR_EVENTS_TOTAL,
    PREPROCESSOR_LATE_EVENTS_DROPPED_TOTAL,
    PREPROCESSOR_PROCESSING_LATENCY_SECONDS,
    PREPROCESSOR_WINDOWS_CLOSED_TOTAL,
)
from dsm_common.schemas import CanonicalEvent, DlqEvent, RunEofEvent
from dsm_core.features import FeaturePipeline
from dsm_core.pipeline import build_window_outputs
from dsm_core.preprocessing import HLEMapper, NoiseFilter
from dsm_core.windowing import ClosedWindow, MultiGranularityWindowManager
from dsm_core.windowing.boundaries import ensure_utc


class StateProtocol(Protocol):
    """Contrato mínimo compatible con `quixstreams.State` para pruebas sin RocksDB."""

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene el valor almacenado bajo `key` o `default` si no existe."""

    def set(self, key: str, value: Any) -> None:
        """Persiste un valor serializable bajo `key`."""

    def delete(self, key: str) -> None:
        """Elimina la entrada asociada a `key`."""


class InMemoryState:
    """Implementación en memoria de `StateProtocol` para pruebas unitarias."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class PreprocessorHandler:
    """Procesa mensajes de `lms.events.canonical` delegando la analítica pura a `dsm_core`."""

    STATE_KEY = "window_state"

    def __init__(
        self,
        hle_catalog: HleCatalogConfig,
        features_config: FeaturesConfig,
        windows_config: WindowsConfig,
        *,
        course_start: datetime | None = None,
        course_end: datetime | None = None,
    ) -> None:
        self._noise_filter = NoiseFilter(hle_catalog)
        self._hle_mapper = HLEMapper(hle_catalog)
        self._feature_pipeline = FeaturePipeline(
            features_config,
            hle_categories=self._hle_mapper.known_hles,
        )
        self._windows_config = windows_config
        self._course_start = ensure_utc(course_start) if course_start is not None else None
        self._course_end = ensure_utc(course_end) if course_end is not None else None

    def _emit_closed_windows(
        self,
        closed_windows: list[ClosedWindow],
        *,
        emitted_at: datetime,
    ) -> list[dict[str, Any]]:
        envelopes: list[dict[str, Any]] = []
        for cw in closed_windows:
            feature_msg, trace_msg = build_window_outputs(
                cw,
                self._feature_pipeline,
                hle_version=self._hle_mapper.version,
                emitted_at=emitted_at,
            )
            PREPROCESSOR_WINDOWS_CLOSED_TOTAL.labels(granularity=cw.granularity).inc()
            envelopes.append(
                {"_target": "features", "payload": feature_msg.model_dump(mode="json")}
            )
            envelopes.append({"_target": "traces", "payload": trace_msg.model_dump(mode="json")})
        return envelopes

    def _persist_manager_state(
        self,
        manager: MultiGranularityWindowManager,
        state: StateProtocol,
    ) -> None:
        serialized = manager.to_state_dict()
        if serialized.get("entries"):
            state.set(self.STATE_KEY, serialized)
        else:
            state.delete(self.STATE_KEY)

    def _make_dlq_envelope(self, raw_value: Any, error_reason: str) -> list[dict[str, Any]]:
        PREPROCESSOR_EVENTS_TOTAL.labels(status="dlq").inc()
        dlq = DlqEvent(
            dlq_id=str(uuid4()),
            received_at=datetime.now(UTC),
            error_reason=error_reason,
            raw_payload=raw_value,
        )
        return [{"_target": "dlq", "payload": dlq.model_dump(mode="json")}]

    def process_record(self, value: Any, state: StateProtocol) -> list[dict[str, Any]]:
        """Procesa un evento canónico o marcador `run_eof` y devuelve mensajes etiquetados."""
        started = perf_counter()
        try:
            if not isinstance(value, dict):
                return self._make_dlq_envelope(
                    value, "El mensaje en lms.events.canonical debe ser un objeto JSON."
                )

            if value.get("event_type") == "run_eof":
                try:
                    eof = RunEofEvent.model_validate(value)
                except ValidationError as exc:
                    return self._make_dlq_envelope(value, f"RunEofEvent inválido: {exc}")

                PREPROCESSOR_EVENTS_TOTAL.labels(status="eof").inc()
                manager = MultiGranularityWindowManager.from_state_dict(
                    state.get(self.STATE_KEY),
                    self._windows_config,
                    course_start=self._course_start,
                    course_end=self._course_end,
                )
                closed_windows = manager.flush_run(eof.run_id, u=eof.u)
                self._persist_manager_state(manager, state)
                return self._emit_closed_windows(closed_windows, emitted_at=datetime.now(UTC))

            try:
                event = CanonicalEvent.model_validate(value)
            except ValidationError as exc:
                return self._make_dlq_envelope(value, f"CanonicalEvent inválido: {exc}")

            if self._noise_filter.is_noise(event):
                PREPROCESSOR_EVENTS_TOTAL.labels(status="noise").inc()
                return []

            enriched = self._hle_mapper.enrich_event(event)
            manager = MultiGranularityWindowManager.from_state_dict(
                state.get(self.STATE_KEY),
                self._windows_config,
                course_start=self._course_start,
                course_end=self._course_end,
            )
            outcome = manager.ingest(enriched)

            for granularity in outcome.dropped_late_granularities:
                PREPROCESSOR_LATE_EVENTS_DROPPED_TOTAL.labels(granularity=granularity).inc()

            if outcome.is_duplicate:
                PREPROCESSOR_EVENTS_TOTAL.labels(status="duplicate").inc()
                return []

            self._persist_manager_state(manager, state)
            PREPROCESSOR_EVENTS_TOTAL.labels(status="mapped").inc()
            return self._emit_closed_windows(
                outcome.closed_windows,
                emitted_at=datetime.now(UTC),
            )
        finally:
            PREPROCESSOR_PROCESSING_LATENCY_SECONDS.observe(perf_counter() - started)
