from __future__ import annotations

from typing import Any, ClassVar

from river.cluster import DBSTREAM

from dsm_core.clustering.base import ClusteringAlgorithm


class DBSTREAMAdapter(ClusteringAlgorithm):
    """Adaptador de ``river.cluster.DBSTREAM`` sobre el contrato ``ClusteringAlgorithm``."""

    name = "dbstream"
    ALLOWED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {
            "clustering_threshold",
            "fading_factor",
            "cleanup_interval",
            "intersection_factor",
            "minimum_weight",
        }
    )
    DEFAULT_PARAMS: ClassVar[dict[str, Any]] = {
        "clustering_threshold": 2.8,
        "fading_factor": 0.05,
        "cleanup_interval": 10,
        "intersection_factor": 0.3,
        "minimum_weight": 1.0,
    }

    def __init__(self, *, seed: int = 42, **params: Any) -> None:
        unknown = set(params) - self.ALLOWED_PARAMS
        if unknown:
            raise ValueError(
                f"Parámetros no soportados para dbstream: {sorted(unknown)}. "
                f"Permitidos: {sorted(self.ALLOWED_PARAMS)}"
            )
        merged = {**self.DEFAULT_PARAMS, **params}
        self.seed = seed
        self._params = merged
        self._model = DBSTREAM(**merged)

    def learn_one(self, x: dict[str, float]) -> None:
        self._model.learn_one(x)

    def predict_one(self, x: dict[str, float]) -> int:
        cluster_id = int(self._model.predict_one(x))
        centers = self._model.centers
        if cluster_id < 0 or cluster_id not in centers:
            return -1
        return cluster_id

    def get_centroid(self, cluster_id: int) -> dict[str, float] | None:
        if cluster_id < 0:
            return None
        centers = self._model.centers
        raw = centers.get(cluster_id)
        if raw is None:
            return None
        return {str(k): float(v) for k, v in raw.items()}

    def snapshot(self) -> dict[str, Any]:
        centers = self._model.centers
        clusters = self._model.clusters
        centroids: dict[str, dict[str, float]] = {}
        cluster_weights: dict[str, float] = {}

        for cid, center in sorted(centers.items()):
            key = str(cid)
            centroids[key] = {str(feat): round(float(val), 6) for feat, val in center.items()}
            cluster_obj = clusters.get(cid)
            weight = float(getattr(cluster_obj, "weight", 0.0)) if cluster_obj is not None else 0.0
            cluster_weights[key] = round(weight, 6)

        micro_clusters = getattr(self._model, "_micro_clusters", {})
        return {
            "algorithm": self.name,
            "initialized": len(centroids) > 0,
            "cluster_count": len(centroids),
            "micro_cluster_count": len(micro_clusters),
            "centroids": centroids,
            "cluster_weights": cluster_weights,
        }
