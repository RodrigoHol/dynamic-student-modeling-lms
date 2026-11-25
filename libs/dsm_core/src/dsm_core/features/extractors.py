"""Extractores de características configurables desde `config/features.yaml`."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from dsm_common.schemas import CanonicalEvent
from dsm_core.features.base import FeatureExtractor

DEFAULT_SESSION_TIMEOUT_SEC = 1800


def group_events_into_sessions(
    events: list[CanonicalEvent],
    inactivity_timeout_sec: int = DEFAULT_SESSION_TIMEOUT_SEC,
) -> list[list[CanonicalEvent]]:
    """Agrupa eventos ordenados en sesiones por `session_hash` o umbral de inactividad."""
    if not events:
        return []

    ordered = sorted(events, key=lambda ev: ev.t)
    if all(ev.M.session_hash for ev in ordered):
        sessions_by_hash: dict[str, list[CanonicalEvent]] = {}
        for ev in ordered:
            sess_id = str(ev.M.session_hash)
            sessions_by_hash.setdefault(sess_id, []).append(ev)
        return list(sessions_by_hash.values())

    sessions: list[list[CanonicalEvent]] = [[ordered[0]]]
    for ev in ordered[1:]:
        prev = sessions[-1][-1]
        gap = (ev.t - prev.t).total_seconds()
        prev_hash = prev.M.session_hash
        curr_hash = ev.M.session_hash
        hash_changed = bool(prev_hash and curr_hash and prev_hash != curr_hash)
        if hash_changed or gap > inactivity_timeout_sec:
            sessions.append([ev])
        else:
            sessions[-1].append(ev)
    return sessions


class TotalEventsExtractor(FeatureExtractor):
    """Cuenta el número total de interacciones válidas en la ventana."""

    name = "total_events"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        return {"total_events": float(len(events))}


class ActiveDaysExtractor(FeatureExtractor):
    """Cuenta el número de días calendario UTC distintos con actividad."""

    name = "active_days"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        days = {ev.t.date() for ev in events}
        return {"active_days": float(len(days))}


class HleFrequencyPerCategoryExtractor(FeatureExtractor):
    """Calcula la frecuencia absoluta de cada categoría HLE dentro de la ventana."""

    name = "hle_frequency_per_category"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        known_categories = window_meta.get("hle_categories") or ()
        counts: dict[str, float] = {
            f"hle_{str(category).lower()}_count": 0.0 for category in known_categories
        }
        for ev in events:
            hle_code = (ev.M.hle or "OTRO").lower()
            key = f"hle_{hle_code}_count"
            counts[key] = counts.get(key, 0.0) + 1.0
        return counts


class RegularityIndexExtractor(FeatureExtractor):
    """Mide regularidad temporal (entropía de Shannon normalizada en `[0.0, 1.0]`)."""

    name = "regularity_index"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        if not events:
            return {"regularity_index": 0.0}

        window_start: datetime = window_meta.get("window_start") or min(ev.t for ev in events)
        window_end: datetime = window_meta.get("window_end") or max(ev.t for ev in events)
        span_seconds = max(0.0, (window_end - window_start).total_seconds())
        n_days = max(1, math.ceil(span_seconds / 86400.0)) if span_seconds > 0 else 1

        if n_days > 1:
            buckets = Counter(ev.t.date() for ev in events)
            total_buckets = n_days
        else:
            buckets = Counter(ev.t.hour for ev in events)
            total_buckets = 24

        total = len(events)
        entropy = 0.0
        for count in buckets.values():
            if count > 0:
                prob = count / total
                entropy -= prob * math.log(prob)

        max_entropy = math.log(total_buckets) if total_buckets > 1 else 0.0
        normalized = (entropy / max_entropy) if max_entropy > 0 else 0.0
        clamped = min(1.0, max(0.0, normalized))
        return {"regularity_index": round(clamped, 6)}


class SessionCountExtractor(FeatureExtractor):
    """Cuenta la cantidad de sesiones de estudio observadas en la ventana."""

    name = "session_count"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        timeout = int(window_meta.get("session_timeout_sec", DEFAULT_SESSION_TIMEOUT_SEC))
        sessions = group_events_into_sessions(events, inactivity_timeout_sec=timeout)
        return {"session_count": float(len(sessions))}


class MeanSessionDurationExtractor(FeatureExtractor):
    """Calcula la duración media de las sesiones en segundos dentro de la ventana."""

    name = "mean_session_duration_sec"

    def compute(
        self,
        events: list[CanonicalEvent],
        window_meta: dict[str, Any],
    ) -> dict[str, float]:
        timeout = int(window_meta.get("session_timeout_sec", DEFAULT_SESSION_TIMEOUT_SEC))
        sessions = group_events_into_sessions(events, inactivity_timeout_sec=timeout)
        if not sessions:
            return {"mean_session_duration_sec": 0.0}
        durations = [(sess[-1].t - sess[0].t).total_seconds() for sess in sessions]
        mean_sec = sum(durations) / len(durations)
        return {"mean_session_duration_sec": round(mean_sec, 6)}
