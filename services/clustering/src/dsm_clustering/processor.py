from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import ValidationError

from dsm_clustering.metrics import (
    CLUSTERING_INGESTED_TO_PROFILE_LATENCY_SECONDS,
    CLUSTERING_OUTLIERS_TOTAL,
    CLUSTERING_PROCESSING_LATENCY_SECONDS,
    CLUSTERING_TRANSITIONS_TOTAL,
    CLUSTERING_VECTORS_TOTAL,
)
from dsm_common.messaging import EventProducer, Topics
from dsm_common.schemas import FeatureVectorMessage, make_dlq_event
from dsm_common.storage import ProfileRepository
from dsm_core.clustering import ClusteringEngine, ClusteringStepResult


class ClusteringServiceProcessor:
    """Orquesta consumo de FeatureVectorMessage, persistencia en MongoDB y emisión a Kafka."""

    def __init__(
        self,
        engine: ClusteringEngine,
        repository: ProfileRepository,
        producer: EventProducer,
    ) -> None:
        self._engine = engine
        self._repository = repository
        self._producer = producer

    @staticmethod
    def assignment_partition_key(granularity: str, window_id: str) -> str:
        return f"{granularity}:{window_id}"

    async def _send_to_dlq(
        self,
        raw_payload: Any,
        reason: str,
        granularity: str = "unknown",
    ) -> None:
        CLUSTERING_VECTORS_TOTAL.labels(status="invalid", granularity=granularity).inc()
        dlq = make_dlq_event(raw_payload, reason)
        await self._producer.publish(
            Topics.DLQ_EVENTS,
            key=dlq.dlq_id,
            value=dlq.model_dump(mode="json"),
        )

    async def handle_raw_payload(self, raw_payload: Any) -> ClusteringStepResult | None:
        started = perf_counter()
        try:
            if not isinstance(raw_payload, dict):
                await self._send_to_dlq(
                    raw_payload,
                    "El mensaje en analytics.features debe ser un objeto JSON.",
                )
                return None

            granularity_hint = str(raw_payload.get("granularity") or "unknown")
            try:
                msg = FeatureVectorMessage.model_validate(raw_payload)
            except ValidationError as exc:
                await self._send_to_dlq(
                    raw_payload,
                    f"FeatureVectorMessage inválido: {exc}",
                    granularity=granularity_hint,
                )
                return None

            result = self._engine.process_vector(msg)
            await self._repository.upsert_profile(result.profile)
            await self._repository.upsert_snapshot(result.snapshot)
            await self._producer.publish(
                Topics.ASSIGNMENTS,
                key=self.assignment_partition_key(msg.granularity, msg.window_id),
                value=result.assignment.model_dump(mode="json"),
            )

            CLUSTERING_VECTORS_TOTAL.labels(status="ok", granularity=msg.granularity).inc()
            if result.assignment.transition_detected:
                CLUSTERING_TRANSITIONS_TOTAL.labels(granularity=msg.granularity).inc()
            if result.assignment.is_outlier:
                CLUSTERING_OUTLIERS_TOTAL.labels(granularity=msg.granularity).inc()
            CLUSTERING_INGESTED_TO_PROFILE_LATENCY_SECONDS.observe(
                result.profile.latencies_ms.ingested_to_profile / 1000.0
            )
            return result
        finally:
            CLUSTERING_PROCESSING_LATENCY_SECONDS.observe(perf_counter() - started)
