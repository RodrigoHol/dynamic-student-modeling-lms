from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dsm_common.schemas import CanonicalEvent

DEFAULT_SESSION_TIMEOUT_SEC = 1800


def group_events_into_sessions(
    events: Sequence[CanonicalEvent],
    inactivity_timeout_sec: int = DEFAULT_SESSION_TIMEOUT_SEC,
) -> list[list[CanonicalEvent]]:
    if not events:
        return []

    is_ordered = all(events[i].t <= events[i + 1].t for i in range(len(events) - 1))
    ordered = list(events) if is_ordered else sorted(events, key=lambda ev: ev.t)

    if all(ev.M.session_hash for ev in ordered):
        sessions_by_hash: dict[str, list[CanonicalEvent]] = {}
        for ev in ordered:
            sessions_by_hash.setdefault(str(ev.M.session_hash), []).append(ev)
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


@dataclass(slots=True)
class WindowContext:
    window_start: datetime | None = None
    window_end: datetime | None = None
    hle_categories: tuple[str, ...] = ()
    session_timeout_sec: int = DEFAULT_SESSION_TIMEOUT_SEC
    _sessions_cache: dict[tuple[int, int], list[list[CanonicalEvent]]] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def sessions_for(self, events: Sequence[CanonicalEvent]) -> list[list[CanonicalEvent]]:
        cache_key = (id(events), len(events))
        cached = self._sessions_cache.get(cache_key)
        if cached is None:
            cached = group_events_into_sessions(
                events,
                inactivity_timeout_sec=self.session_timeout_sec,
            )
            self._sessions_cache[cache_key] = cached
        return cached

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
        *,
        default_categories: tuple[str, ...] = (),
    ) -> WindowContext:
        raw = data or {}
        cats = raw.get("hle_categories")
        return cls(
            window_start=raw.get("window_start"),
            window_end=raw.get("window_end"),
            hle_categories=tuple(cats) if cats is not None else default_categories,
            session_timeout_sec=int(raw.get("session_timeout_sec", DEFAULT_SESSION_TIMEOUT_SEC)),
        )


class FeatureExtractor(ABC):
    name: str

    @abstractmethod
    def compute(
        self,
        events: Sequence[CanonicalEvent],
        context: WindowContext,
    ) -> dict[str, float]: ...
