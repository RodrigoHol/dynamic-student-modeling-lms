from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from dsm_common.schemas import CanonicalEvent
from dsm_core.features.base import (
    DEFAULT_SESSION_TIMEOUT_SEC,
    FeatureExtractor,
    WindowContext,
    group_events_into_sessions,
)

__all__ = [
    "DEFAULT_SESSION_TIMEOUT_SEC",
    "ActiveDaysExtractor",
    "HleFrequencyPerCategoryExtractor",
    "MeanSessionDurationExtractor",
    "RegularityIndexExtractor",
    "SessionCountExtractor",
    "TotalEventsExtractor",
    "group_events_into_sessions",
]


class TotalEventsExtractor(FeatureExtractor):
    name = "total_events"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        return {"total_events": float(len(events))}


class ActiveDaysExtractor(FeatureExtractor):
    name = "active_days"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        return {"active_days": float(len({ev.t.date() for ev in events}))}


class HleFrequencyPerCategoryExtractor(FeatureExtractor):
    name = "hle_frequency_per_category"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        counts: dict[str, float] = {
            f"hle_{str(category).lower()}_count": 0.0 for category in context.hle_categories
        }
        for ev in events:
            key = f"hle_{(ev.M.hle or 'OTRO').lower()}_count"
            counts[key] = counts.get(key, 0.0) + 1.0
        return counts


class RegularityIndexExtractor(FeatureExtractor):
    """Entropía de Shannon normalizada en `[0.0, 1.0]` sobre días (o horas si Δt <= 1 día)."""

    name = "regularity_index"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        if not events:
            return {"regularity_index": 0.0}

        window_start: datetime = context.window_start or min(ev.t for ev in events)
        window_end: datetime = context.window_end or max(ev.t for ev in events)
        span_seconds = max(0.0, (window_end - window_start).total_seconds())
        n_days = max(1, math.ceil(span_seconds / 86400.0)) if span_seconds > 0 else 1

        if n_days > 1:
            buckets = Counter(ev.t.date() for ev in events)
            total_buckets = n_days
        else:
            buckets = Counter(ev.t.hour for ev in events)
            total_buckets = 24

        total = len(events)
        entropy = sum(
            -(count / total) * math.log(count / total) for count in buckets.values() if count > 0
        )
        max_entropy = math.log(total_buckets) if total_buckets > 1 else 0.0
        normalized = (entropy / max_entropy) if max_entropy > 0 else 0.0
        return {"regularity_index": round(min(1.0, max(0.0, normalized)), 6)}


class SessionCountExtractor(FeatureExtractor):
    name = "session_count"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        return {"session_count": float(len(context.sessions_for(events)))}


class MeanSessionDurationExtractor(FeatureExtractor):
    name = "mean_session_duration_sec"

    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]:
        sessions = context.sessions_for(events)
        if not sessions:
            return {"mean_session_duration_sec": 0.0}
        total_sec = sum((sess[-1].t - sess[0].t).total_seconds() for sess in sessions)
        return {"mean_session_duration_sec": round(total_sec / len(sessions), 6)}
