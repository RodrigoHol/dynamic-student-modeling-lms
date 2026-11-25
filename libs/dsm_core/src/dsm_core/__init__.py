"""Dominio analítico puro para Dynamic Student Modeling LMS (ADR-10)."""

from dsm_core.features import (
    FEATURE_EXTRACTOR_REGISTRY,
    ActiveDaysExtractor,
    FeatureExtractor,
    FeaturePipeline,
    HleFrequencyPerCategoryExtractor,
    MeanSessionDurationExtractor,
    RegularityIndexExtractor,
    SessionCountExtractor,
    TotalEventsExtractor,
    create_feature_extractor,
    group_events_into_sessions,
)
from dsm_core.pipeline import (
    PreprocessingEngine,
    ProcessEventResult,
    build_window_outputs,
    window_partition_key,
)
from dsm_core.preprocessing import HLEMapper, NoiseFilter, extract_match_context, rule_matches
from dsm_core.windowing import (
    ClosedWindow,
    MultiGranularityWindowManager,
    WindowAssignmentOutcome,
    WindowSpec,
    compute_window_spec,
)

__version__ = "0.1.0"

__all__ = [
    "ActiveDaysExtractor",
    "ClosedWindow",
    "FEATURE_EXTRACTOR_REGISTRY",
    "FeatureExtractor",
    "FeaturePipeline",
    "HLEMapper",
    "HleFrequencyPerCategoryExtractor",
    "MeanSessionDurationExtractor",
    "MultiGranularityWindowManager",
    "NoiseFilter",
    "PreprocessingEngine",
    "ProcessEventResult",
    "RegularityIndexExtractor",
    "SessionCountExtractor",
    "TotalEventsExtractor",
    "WindowAssignmentOutcome",
    "WindowSpec",
    "__version__",
    "build_window_outputs",
    "compute_window_spec",
    "create_feature_extractor",
    "extract_match_context",
    "group_events_into_sessions",
    "rule_matches",
    "window_partition_key",
]
