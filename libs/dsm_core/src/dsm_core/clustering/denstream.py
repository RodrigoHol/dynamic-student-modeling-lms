from __future__ import annotations

from typing import Any, ClassVar

from river.cluster import DenStream

from dsm_core.clustering.base import ClusteringAlgorithm


class DenStreamAdapter(ClusteringAlgorithm):
    """Adaptador de ``river.cluster.DenStream`` sobre el contrato ``ClusteringAlgorithm``."""

    name = "denstream"
    ALLOWED_PARAMS: ClassVar[frozenset[str]] = frozenset(
        {"decaying_factor", "beta", "mu", "epsilon", "n_samples_init", "stream_speed"}
    )
    DEFAULT_PARAMS: ClassVar[dict[str, Any]] = {
        "decaying_factor": 0.05,
        "beta": 0.75,
        "mu": 2.0,
        "epsilon": 2.8,
        "n_samples_init": 10,
        "stream_speed": 100,
    }

    def __init__(self, *, seed: int = 42, **params: Any) -> None:
        unknown = set(params) - self.ALLOWED_PARAMS
        if unknown:
            raise ValueError(
                f"Parámetros no soportados para denstream: {sorted(unknown)}. "
                f"Permitidos: {sorted(self.ALLOWED_PARAMS)}"
            )
        merged = {**self.DEFAULT_PARAMS, **params}
        # Invariante de DenStream (River): log((mu * beta) / (mu * beta - 1)) exige mu * beta > 1.
        if float(merged["mu"]) * float(merged["beta"]) <= 1.0:
            raise ValueError(
                "DenStream requiere mu * beta > 1.0 "
                f"(recibido mu={merged['mu']}, beta={merged['beta']})."
            )
        self.seed = seed
        self._params = merged
        self._model = DenStream(**merged)

    def learn_one(self, x: dict[str, float]) -> None:
        self._model.learn_one(x)

    def predict_one(self, x: dict[str, float]) -> int:
        if not self._model.initialized:
            return -1
        cluster_id = int(self._model.predict_one(x))
        if cluster_id < 0 or cluster_id not in self._model.clusters:
            return -1
        return cluster_id

    def get_centroid(self, cluster_id: int) -> dict[str, float] | None:
        if cluster_id < 0 or not self._model.clusters:
            return None
        centers = self._model.centers
        raw = centers.get(cluster_id)
        if raw is None:
            return None
        return {str(k): float(v) for k, v in raw.items()}

    def snapshot(self) -> dict[str, Any]:
        centers = self._model.centers if self._model.clusters else {}
        centroids: dict[str, dict[str, float]] = {}
        cluster_weights: dict[str, float] = {}
        ts = self._model.timestamp

        for cid, center in sorted(centers.items()):
            key = str(cid)
            centroids[key] = {str(feat): round(float(val), 6) for feat, val in center.items()}
            cluster_obj = self._model.clusters.get(cid)
            if cluster_obj is not None and hasattr(cluster_obj, "calc_weight"):
                weight = float(cluster_obj.calc_weight(ts))
            else:
                weight = float(getattr(cluster_obj, "weight", 0.0))
            cluster_weights[key] = round(weight, 6)

        p_count = len(self._model.p_micro_clusters)
        o_count = len(self._model.o_micro_clusters)
        return {
            "algorithm": self.name,
            "initialized": bool(self._model.initialized),
            "cluster_count": len(centroids),
            "micro_cluster_count": p_count + o_count,
            "p_micro_cluster_count": p_count,
            "o_micro_cluster_count": o_count,
            "centroids": centroids,
            "cluster_weights": cluster_weights,
        }
