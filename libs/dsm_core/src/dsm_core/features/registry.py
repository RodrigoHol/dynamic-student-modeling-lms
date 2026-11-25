from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dsm_common.config import FeaturesConfig
from dsm_common.schemas import CanonicalEvent
from dsm_core.features.base import FeatureExtractor, WindowContext
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
    if name not in FEATURE_EXTRACTOR_REGISTRY:
        supported = ", ".join(sorted(FEATURE_EXTRACTOR_REGISTRY))
        raise ValueError(f"Extractor '{name}' no registrado. Disponibles: {supported}")
    return FEATURE_EXTRACTOR_REGISTRY[name]()


class FeaturePipeline:
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
        events: Sequence[CanonicalEvent],
        window_meta: WindowContext | Mapping[str, Any] | None = None,
    ) -> dict[str, float]:
        if isinstance(window_meta, WindowContext):
            if window_meta.hle_categories or not self.hle_categories:
                context = window_meta
            else:
                context = WindowContext(
                    window_start=window_meta.window_start,
                    window_end=window_meta.window_end,
                    hle_categories=self.hle_categories,
                    session_timeout_sec=window_meta.session_timeout_sec,
                )
        else:
            context = WindowContext.from_mapping(
                window_meta,
                default_categories=self.hle_categories,
            )

        features: dict[str, float] = {}
        for extractor in self.extractors:
            features.update(extractor.compute(events, context))
        return features
