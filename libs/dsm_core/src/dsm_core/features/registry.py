"""Registro declarativo y pipeline de extractores de características."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dsm_common.config import FeaturesConfig
from dsm_common.schemas import CanonicalEvent
from dsm_core.features.base import FeatureExtractor
from dsm_core.features.extractors import (
    ActiveDaysExtractor,
    HleFrequencyPerCategoryExtractor,
    MeanSessionDurationExtractor,
    RegularityIndexExtractor,
    SessionCountExtractor,
    TotalEventsExtractor,
)

FEATURE_EXTRACTOR_REGISTRY: dict[str, type[FeatureExtractor]] = {
    "total_events": TotalEventsExtractor,
    "active_days": ActiveDaysExtractor,
    "hle_frequency_per_category": HleFrequencyPerCategoryExtractor,
    "regularity_index": RegularityIndexExtractor,
    "session_count": SessionCountExtractor,
    "mean_session_duration_sec": MeanSessionDurationExtractor,
}


def create_feature_extractor(name: str) -> FeatureExtractor:
    """Instancia un extractor registrado desde su nombre en `config/features.yaml`."""
    if name not in FEATURE_EXTRACTOR_REGISTRY:
        supported = ", ".join(sorted(FEATURE_EXTRACTOR_REGISTRY))
        raise ValueError(f"Extractor '{name}' no registrado. Disponibles: {supported}")
    return FEATURE_EXTRACTOR_REGISTRY[name]()


class FeaturePipeline:
    """Ejecuta en orden los extractores habilitados en `config/features.yaml`."""

    def __init__(
        self,
        config: FeaturesConfig,
        *,
        hle_categories: Sequence[str] = (),
    ) -> None:
        self.version: str = config.version
        self.hle_categories: tuple[str, ...] = tuple(hle_categories)
        self.extractors: tuple[FeatureExtractor, ...] = tuple(
            create_feature_extractor(name) for name in config.enabled_extractors
        )

    def extract(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        """Computa el vector completo `{feature: valor}` para una ventana."""
        meta: dict[str, Any] = dict(window_meta or {})
        if self.hle_categories and "hle_categories" not in meta:
            meta["hle_categories"] = self.hle_categories

        features: dict[str, float] = {}
        for extractor in self.extractors:
            features.update(extractor.compute(events, meta))
        return features
