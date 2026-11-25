from __future__ import annotations

import math
from collections.abc import Mapping

from dsm_common.schemas import ExplainabilityFeature


class OnlineFeatureStats:
    """Estadísticas incrementales por característica mediante el algoritmo de Welford."""

    def __init__(self) -> None:
        self._count: int = 0
        self._means: dict[str, float] = {}
        self._m2: dict[str, float] = {}

    @property
    def count(self) -> int:
        return self._count

    def update(self, features: Mapping[str, float]) -> None:
        self._count += 1
        for key, raw_val in features.items():
            val = float(raw_val)
            prev_mean = self._means.get(key, 0.0)
            delta = val - prev_mean
            new_mean = prev_mean + delta / self._count
            delta2 = val - new_mean
            self._means[key] = new_mean
            self._m2[key] = self._m2.get(key, 0.0) + delta * delta2

    def mean(self, feature: str) -> float:
        return self._means.get(feature, 0.0)

    def std(self, feature: str) -> float:
        if self._count < 2:
            return 0.0
        variance = self._m2.get(feature, 0.0) / self._count
        return math.sqrt(max(0.0, variance))

    def standardize(self, features: Mapping[str, float]) -> dict[str, float]:
        scaled: dict[str, float] = {}
        for key, raw_val in features.items():
            val = float(raw_val)
            mu = self.mean(key)
            sigma = self.std(key)
            if sigma > 1e-9:
                scaled[key] = (val - mu) / sigma
            else:
                scaled[key] = val - mu
        return scaled

    def unstandardize(self, scaled_features: Mapping[str, float]) -> dict[str, float]:
        original: dict[str, float] = {}
        for key, raw_val in scaled_features.items():
            val = float(raw_val)
            mu = self.mean(key)
            sigma = self.std(key)
            original[key] = mu + val * sigma if sigma > 1e-9 else mu + val
        return original


def compute_top_contributing_features(
    features: Mapping[str, float],
    centroid_model_space: Mapping[str, float] | None,
    stats: OnlineFeatureStats,
    *,
    is_outlier: bool,
    scaled: bool = True,
    top_k: int = 3,
) -> list[ExplainabilityFeature]:
    """Calcula las características más distintivas del estudiante mediante ``z_score``.

    Fórmula:
    - Cuando existe centroide válido (``not is_outlier and centroid_model_space is not None``),
      se mide la desviación normalizada respecto al centroide asignado:
      ``z_centroid(f) = x_scaled(f) - c_scaled(f)`` (o ``(x(f) - c(f)) / std(f)`` si no hubo
      escalado previo). Si el punto coincide exactamente con el centroide (p. ej. primer
      elemento del clúster), se utiliza el ``z_score`` poblacional respecto a la media global
      para conservar explicabilidad informativa.
    - Para outliers (``cluster_id == -1``) o ausencia de centroide, se utiliza el ``z_score``
      poblacional: ``(x(f) - mean(f)) / std(f)``.
    """
    if top_k <= 0 or not features:
        return []

    population_z: dict[str, float] = {}
    for key, raw_val in features.items():
        val = float(raw_val)
        sigma = stats.std(key)
        population_z[key] = ((val - stats.mean(key)) / sigma) if sigma > 1e-9 else 0.0

    scores: dict[str, float] = {}
    if not is_outlier and centroid_model_space is not None:
        x_scaled = stats.standardize(features) if scaled else None
        for key, raw_val in features.items():
            c_val = float(centroid_model_space.get(key, 0.0))
            if scaled and x_scaled is not None:
                scores[key] = x_scaled[key] - c_val
            else:
                sigma = stats.std(key)
                diff = float(raw_val) - c_val
                scores[key] = (diff / sigma) if sigma > 1e-9 else diff
        if all(abs(score) <= 1e-9 for score in scores.values()):
            scores = population_z
    else:
        scores = population_z

    ranked = sorted(
        scores.items(),
        key=lambda item: (-abs(item[1]), item[0]),
    )
    return [
        ExplainabilityFeature(feature=name, z_score=round(score, 4))
        for name, score in ranked[:top_k]
    ]
