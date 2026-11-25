from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from dsm_common.config import FeaturesConfig, HleCatalogConfig, WindowsConfig
from dsm_common.schemas import (
    CanonicalEvent,
    FeatureVectorMessage,
    RunEofEvent,
    TraceMessage,
    make_dlq_event,
)
from dsm_core.pipeline import PreprocessingEngine
from dsm_core.windowing import KeyValueState
from dsm_preprocessor.metrics import (
    PREPROCESSOR_EVENTS_TOTAL,
    PREPROCESSOR_LATE_EVENTS_DROPPED_TOTAL,
    PREPROCESSOR_PROCESSING_LATENCY_SECONDS,
    PREPROCESSOR_WINDOWS_CLOSED_TOTAL,
)

StateProtocol = KeyValueState


class InMemoryState:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class PreprocessorHandler:
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
        self._engine = PreprocessingEngine(
            hle_catalog,
            features_config,
            windows_config,
            course_start=course_start,
            course_end=course_end,
        )

    def _to_envelopes(
        self,
        outputs: list[tuple[FeatureVectorMessage, TraceMessage]],
    ) -> list[dict[str, Any]]:
        envelopes: list[dict[str, Any]] = []
        for feature_msg, trace_msg in outputs:
            PREPROCESSOR_WINDOWS_CLOSED_TOTAL.labels(granularity=feature_msg.granularity).inc()
            envelopes.append(
                {"_target": "features", "payload": feature_msg.model_dump(mode="json")}
            )
            envelopes.append(
                {"_target": "traces", "payload": trace_msg.model_dump(mode="json")}
            )
        return envelopes

    def _make_dlq_envelope(self, raw_value: Any, error_reason: str) -> list[dict[str, Any]]:
        PREPROCESSOR_EVENTS_TOTAL.labels(status="dlq").inc()
        dlq = make_dlq_event(raw_value, error_reason)
        return [{"_target": "dlq", "payload": dlq.model_dump(mode="json")}]

    def process_record(self, value: Any, state: KeyValueState) -> list[dict[str, Any]]:
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
                outputs = self._engine.flush_run_with_state(
                    eof.run_id, state, u=eof.u, state_key=self.STATE_KEY
                )
                return self._to_envelopes(outputs)

            try:
                event = CanonicalEvent.model_validate(value)
            except ValidationError as exc:
                return self._make_dlq_envelope(value, f"CanonicalEvent inválido: {exc}")

            result = self._engine.process_event_with_state(
                event, state, state_key=self.STATE_KEY
            )
            for granularity in result.dropped_late_granularities:
                PREPROCESSOR_LATE_EVENTS_DROPPED_TOTAL.labels(granularity=granularity).inc()

            PREPROCESSOR_EVENTS_TOTAL.labels(status=result.status).inc()
            return self._to_envelopes(result.outputs)
        finally:
            PREPROCESSOR_PROCESSING_LATENCY_SECONDS.observe(perf_counter() - started)
