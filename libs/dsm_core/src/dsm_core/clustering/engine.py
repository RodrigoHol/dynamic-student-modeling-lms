from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dsm_common.config import ClusteringConfig
from dsm_common.schemas import (
    ClusterAssignmentMessage,
    ClusteringResultMeta,
    ClusterSnapshotDocument,
    FeatureVectorMessage,
    ProfileLatenciesMs,
    StudentProfileDocument,
)
from dsm_common.time import ensure_utc, utc_now
from dsm_core.clustering.base import ClusteringAlgorithm
from dsm_core.clustering.registry import create_clustering_model, resolve_clustering_params
from dsm_core.explainability import (
    OnlineFeatureStats,
    TransitionTracker,
    compute_top_contributing_features,
)


@dataclass(slots=True)
class ClusteringStepResult:
    profile: StudentProfileDocument
    snapshot: ClusterSnapshotDocument
    assignment: ClusterAssignmentMessage


@dataclass(slots=True)
class _GranularityState:
    model: ClusteringAlgorithm
    stats: OnlineFeatureStats = field(default_factory=OnlineFeatureStats)
    transitions: TransitionTracker = field(default_factory=TransitionTracker)


class ClusteringEngine:
    """Motor puro de clustering evolutivo aislado por ``(run_id, granularity)``."""

    def __init__(self, config: ClusteringConfig) -> None:
        self._config = config
        self._algorithm_name = config.algorithm.strip().lower()
        self._resolved_params = resolve_clustering_params(config)
        # Validación fail-fast al arranque de parámetros y algoritmo.
        create_clustering_model(self._algorithm_name, self._resolved_params, seed=config.seed)
        self._states: dict[tuple[str, str], _GranularityState] = {}

    @property
    def algorithm_name(self) -> str:
        return self._algorithm_name

    @property
    def resolved_params(self) -> dict[str, Any]:
        return dict(self._resolved_params)

    def _get_or_create_state(self, run_id: str, granularity: str) -> _GranularityState:
        key = (run_id, granularity)
        state = self._states.get(key)
        if state is None:
            model = create_clustering_model(
                self._algorithm_name,
                self._resolved_params,
                seed=self._config.seed,
            )
            state = _GranularityState(model=model)
            self._states[key] = state
        return state

    def _unstandardize_centroids(
        self,
        raw_centroids: dict[str, dict[str, float]],
        stats: OnlineFeatureStats,
    ) -> dict[str, dict[str, float]]:
        if not self._config.scale_features:
            return raw_centroids
        return {
            cid: {
                feat: round(val, 6)
                for feat, val in stats.unstandardize(centroid).items()
            }
            for cid, centroid in raw_centroids.items()
        }

    def process_vector(
        self,
        msg: FeatureVectorMessage,
        *,
        processed_at: datetime | None = None,
    ) -> ClusteringStepResult:
        now = ensure_utc(processed_at) if processed_at is not None else utc_now()
        state = self._get_or_create_state(msg.run_id, msg.granularity)

        clean_features = {k: float(v) for k, v in msg.features.items()}
        state.stats.update(clean_features)
        x_model = (
            state.stats.standardize(clean_features)
            if self._config.scale_features
            else clean_features
        )

        state.model.learn_one(x_model)
        cluster_id = state.model.predict_one(x_model)
        is_outlier = cluster_id < 0
        centroid_model = None if is_outlier else state.model.get_centroid(cluster_id)
        distance = state.model.distance_to_centroid(x_model, cluster_id)

        transition = state.transitions.record(
            student_id=msg.u,
            window_id=msg.window_id,
            window_start=msg.window_start,
            cluster_id=cluster_id,
        )
        top_features = compute_top_contributing_features(
            clean_features,
            centroid_model,
            state.stats,
            is_outlier=is_outlier,
            scaled=self._config.scale_features,
            top_k=self._config.top_k_features,
        )

        latency_ms = max(0, int((now - msg.last_event_ingested_at).total_seconds() * 1000))
        profile_id = f"{msg.run_id}:{msg.granularity}:{msg.window_id}:{msg.u}"
        profile = StudentProfileDocument(
            _id=profile_id,
            run_id=msg.run_id,
            course_id=msg.course_id,
            student_id=msg.u,
            granularity=msg.granularity,
            window_id=msg.window_id,
            window_start=msg.window_start,
            window_end=msg.window_end,
            features_version=msg.features_version,
            features=clean_features,
            clustering=ClusteringResultMeta(
                algorithm=self._algorithm_name,
                cluster_id=cluster_id,
                previous_cluster_id=transition.previous_cluster_id,
                transition_detected=transition.transition_detected,
                distance_to_centroid=distance,
                is_outlier=is_outlier,
            ),
            explainability={"top_contributing_features": top_features},
            latencies_ms=ProfileLatenciesMs(ingested_to_profile=latency_ms),
            updated_at=now,
        )

        raw_snapshot = state.model.snapshot()
        raw_centroids = raw_snapshot.get("centroids", {})
        readable_centroids = self._unstandardize_centroids(raw_centroids, state.stats)
        snapshot_id = f"{msg.run_id}:{msg.granularity}:{msg.window_id}"
        snapshot_doc = ClusterSnapshotDocument(
            _id=snapshot_id,
            run_id=msg.run_id,
            course_id=msg.course_id,
            granularity=msg.granularity,
            window_id=msg.window_id,
            window_start=msg.window_start,
            window_end=msg.window_end,
            algorithm=self._algorithm_name,
            cluster_count=int(raw_snapshot.get("cluster_count", 0)),
            micro_cluster_count=int(raw_snapshot.get("micro_cluster_count", 0)),
            centroids=readable_centroids,
            cluster_weights=dict(raw_snapshot.get("cluster_weights", {})),
            snapshot=raw_snapshot,
            updated_at=now,
        )

        assignment = ClusterAssignmentMessage(
            run_id=msg.run_id,
            course_id=msg.course_id,
            u=msg.u,
            granularity=msg.granularity,
            window_id=msg.window_id,
            window_start=msg.window_start,
            window_end=msg.window_end,
            algorithm=self._algorithm_name,
            cluster_id=cluster_id,
            previous_cluster_id=transition.previous_cluster_id,
            transition_detected=transition.transition_detected,
            distance_to_centroid=distance,
            is_outlier=is_outlier,
            last_event_ingested_at=msg.last_event_ingested_at,
            emitted_at=now,
        )

        return ClusteringStepResult(
            profile=profile,
            snapshot=snapshot_doc,
            assignment=assignment,
        )
