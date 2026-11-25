from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from dsm_common.config import WindowsConfig
from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo
from dsm_common.time import ensure_utc
from dsm_core.windowing.boundaries import WindowSpec, compute_window_spec

_METADATA_FIELDS = frozenset(EventMetadata.model_fields)


class KeyValueState(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


@dataclass(slots=True)
class ClosedWindow:
    run_id: str
    course_id: str
    u: str
    granularity: str
    window_id: str
    window_start: datetime
    window_end: datetime
    events: list[CanonicalEvent]
    last_event_ingested_at: datetime


@dataclass(slots=True)
class WindowAssignmentOutcome:
    closed_windows: list[ClosedWindow] = field(default_factory=list)
    dropped_late_granularities: list[str] = field(default_factory=list)
    is_duplicate: bool = False


def _event_state_key(run_id: str, event_id: str) -> str:
    return f"ev:{run_id}:{event_id}"


def _dump_event_compact(event: CanonicalEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "u": event.u,
        "a": event.a,
        "r": {
            "resource_id": event.r.resource_id,
            "resource_type": event.r.resource_type,
            "name": event.r.name,
        },
        "t": event.t.isoformat(),
        "ingested_at": event.ingested_at.isoformat(),
        "M": event.M.model_dump(mode="json", exclude_none=True),
    }


def _load_event_compact(data: dict[str, Any]) -> CanonicalEvent:
    r_data = data["r"]
    m_data = data["M"]
    m_known = {k: v for k, v in m_data.items() if k in _METADATA_FIELDS}
    m_extra = {k: v for k, v in m_data.items() if k not in _METADATA_FIELDS}

    resource = ResourceInfo.model_construct(
        resource_id=r_data["resource_id"],
        resource_type=r_data["resource_type"],
        name=r_data.get("name"),
    )
    metadata = EventMetadata.model_construct(_fields_set=set(m_known), **m_known)
    object.__setattr__(metadata, "__pydantic_extra__", m_extra)

    return CanonicalEvent.model_construct(
        event_id=data["event_id"],
        run_id=data["run_id"],
        u=data["u"],
        a=data["a"],
        r=resource,
        t=ensure_utc(datetime.fromisoformat(data["t"])),
        ingested_at=ensure_utc(datetime.fromisoformat(data["ingested_at"])),
        M=metadata,
    )


@dataclass(slots=True)
class _WindowBucket:
    run_id: str
    course_id: str
    u: str
    granularity: str
    window_id: str
    window_start: datetime
    window_end: datetime
    close_on_eof: bool
    fixed_bounds: bool
    last_event_ingested_at: datetime
    event_ids: list[str] = field(default_factory=list)
    seen_event_ids: set[str] = field(default_factory=set)

    def add_event(self, event: CanonicalEvent) -> bool:
        if event.event_id in self.seen_event_ids:
            return False
        self.seen_event_ids.add(event.event_id)
        self.event_ids.append(event.event_id)
        if not self.fixed_bounds:
            if event.t < self.window_start:
                self.window_start = event.t
            if event.t > self.window_end:
                self.window_end = event.t
        if event.ingested_at > self.last_event_ingested_at:
            self.last_event_ingested_at = event.ingested_at
        return True

    def to_closed_window(self, events_by_id: dict[str, CanonicalEvent]) -> ClosedWindow:
        ordered_events = sorted(
            (events_by_id[eid] for eid in self.event_ids),
            key=lambda ev: ev.t,
        )
        return ClosedWindow(
            run_id=self.run_id,
            course_id=self.course_id,
            u=self.u,
            granularity=self.granularity,
            window_id=self.window_id,
            window_start=self.window_start,
            window_end=self.window_end,
            events=ordered_events,
            last_event_ingested_at=self.last_event_ingested_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "course_id": self.course_id,
            "u": self.u,
            "granularity": self.granularity,
            "window_id": self.window_id,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "close_on_eof": self.close_on_eof,
            "fixed_bounds": self.fixed_bounds,
            "last_event_ingested_at": self.last_event_ingested_at.isoformat(),
            "event_ids": self.event_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _WindowBucket:
        event_ids = list(data.get("event_ids", []))
        return cls(
            run_id=data["run_id"],
            course_id=data["course_id"],
            u=data["u"],
            granularity=data["granularity"],
            window_id=data["window_id"],
            window_start=ensure_utc(datetime.fromisoformat(data["window_start"])),
            window_end=ensure_utc(datetime.fromisoformat(data["window_end"])),
            close_on_eof=bool(data["close_on_eof"]),
            fixed_bounds=bool(data["fixed_bounds"]),
            last_event_ingested_at=ensure_utc(
                datetime.fromisoformat(data["last_event_ingested_at"])
            ),
            event_ids=event_ids,
            seen_event_ids=set(event_ids),
        )


@dataclass(slots=True)
class _StudentRunState:
    watermark: datetime
    open_windows: dict[tuple[str, str], _WindowBucket] = field(default_factory=dict)
    events_by_id: dict[str, CanonicalEvent] = field(default_factory=dict)

    def referenced_event_ids(self) -> set[str]:
        return {eid for bucket in self.open_windows.values() for eid in bucket.event_ids}

    def to_index_dict(self) -> dict[str, Any]:
        return {
            "watermark": self.watermark.isoformat(),
            "open_windows": [bucket.to_dict() for bucket in self.open_windows.values()],
        }

    def to_full_dict(self) -> dict[str, Any]:
        payload = self.to_index_dict()
        payload["events"] = {
            eid: _dump_event_compact(ev) for eid, ev in self.events_by_id.items()
        }
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _StudentRunState:
        open_windows: dict[tuple[str, str], _WindowBucket] = {}
        for item in data.get("open_windows", []):
            bucket = _WindowBucket.from_dict(item)
            open_windows[(bucket.granularity, bucket.window_id)] = bucket
        events_by_id = {
            eid: _load_event_compact(raw_ev)
            for eid, raw_ev in data.get("events", {}).items()
        }
        return cls(
            watermark=ensure_utc(datetime.fromisoformat(data["watermark"])),
            open_windows=open_windows,
            events_by_id=events_by_id,
        )


class MultiGranularityWindowManager:
    """Administra ventanas disjuntas simultáneas por tiempo del evento `t` y watermark."""

    def __init__(
        self,
        config: WindowsConfig,
        *,
        course_start: datetime | None = None,
        course_end: datetime | None = None,
    ) -> None:
        self._config = config
        self._grace = timedelta(seconds=config.grace_period_seconds)
        self._course_start = ensure_utc(course_start) if course_start is not None else None
        self._course_end = ensure_utc(course_end) if course_end is not None else None
        self._granularity_rank = {
            name: idx for idx, name in enumerate(config.active_granularities)
        }
        self._states: dict[tuple[str, str], _StudentRunState] = {}

        for granularity in config.active_granularities:
            if granularity not in config.windows:
                raise ValueError(
                    f"Granularidad '{granularity}' declarada en active_granularities "
                    "no existe en windows."
                )

    def _sort_closed_windows(self, closed: list[ClosedWindow]) -> list[ClosedWindow]:
        return sorted(
            closed,
            key=lambda w: (
                self._granularity_rank.get(w.granularity, 999),
                w.window_start,
                w.window_id,
                w.u,
            ),
        )

    def _should_close_on_watermark(self, bucket: _WindowBucket, watermark: datetime) -> bool:
        if bucket.close_on_eof and not (bucket.granularity == "course" and bucket.fixed_bounds):
            return False
        return watermark >= (bucket.window_end + self._grace)

    def _assign_event_to_state(
        self,
        state: _StudentRunState,
        event: CanonicalEvent,
    ) -> tuple[list[str], bool, bool, list[_WindowBucket]]:
        if event.t > state.watermark:
            state.watermark = event.t

        dropped_late: list[str] = []
        added_any = False
        saw_duplicate = False

        for granularity in self._config.active_granularities:
            definition = self._config.windows[granularity]
            spec: WindowSpec = compute_window_spec(
                event.t,
                granularity,
                definition,
                course_id=event.M.course_id,
                course_start=self._course_start,
                course_end=self._course_end,
            )

            # Cualquier ventana cuya fecha de cierre + gracia ya fue superada por el watermark
            # se descarta directamente en esa granularidad para evitar almacenar estado vencido.
            if not spec.close_on_eof and state.watermark >= (spec.window_end + self._grace):
                dropped_late.append(granularity)
                continue

            if (
                spec.close_on_eof
                and spec.granularity == "course"
                and spec.fixed_bounds
                and state.watermark >= (spec.window_end + self._grace)
            ):
                dropped_late.append(granularity)
                continue

            win_key = (spec.granularity, spec.window_id)
            bucket = state.open_windows.get(win_key)
            if bucket is None:
                bucket = _WindowBucket(
                    run_id=event.run_id,
                    course_id=event.M.course_id,
                    u=event.u,
                    granularity=spec.granularity,
                    window_id=spec.window_id,
                    window_start=spec.window_start,
                    window_end=spec.window_end,
                    close_on_eof=spec.close_on_eof,
                    fixed_bounds=spec.fixed_bounds,
                    last_event_ingested_at=event.ingested_at,
                )
                state.open_windows[win_key] = bucket

            if bucket.add_event(event):
                added_any = True
            else:
                saw_duplicate = True

        keys_to_close = [
            win_key
            for win_key, bucket in state.open_windows.items()
            if self._should_close_on_watermark(bucket, state.watermark)
        ]
        closing_buckets = [state.open_windows.pop(win_key) for win_key in keys_to_close]
        return dropped_late, added_any, saw_duplicate, closing_buckets

    def ingest(self, event: CanonicalEvent) -> WindowAssignmentOutcome:
        state_key = (event.run_id, event.u)
        state = self._states.get(state_key)
        if state is None:
            state = _StudentRunState(watermark=event.t)
            self._states[state_key] = state

        dropped_late, added_any, saw_duplicate, closing_buckets = self._assign_event_to_state(
            state, event
        )
        if added_any:
            state.events_by_id[event.event_id] = event

        closed_windows = [bucket.to_closed_window(state.events_by_id) for bucket in closing_buckets]
        if closing_buckets:
            referenced = state.referenced_event_ids()
            for obsolete_id in set(state.events_by_id) - referenced:
                del state.events_by_id[obsolete_id]

        return WindowAssignmentOutcome(
            closed_windows=self._sort_closed_windows(closed_windows),
            dropped_late_granularities=dropped_late,
            is_duplicate=(saw_duplicate and not added_any),
        )

    def flush_run(self, run_id: str, u: str | None = None) -> list[ClosedWindow]:
        matching_keys = [
            key
            for key in self._states
            if key[0] == run_id and (u is None or key[1] == u)
        ]
        closed_windows: list[ClosedWindow] = []
        for state_key in matching_keys:
            state = self._states.pop(state_key)
            for bucket in state.open_windows.values():
                closed_windows.append(bucket.to_closed_window(state.events_by_id))
        return self._sort_closed_windows(closed_windows)

    def ingest_with_state(
        self,
        event: CanonicalEvent,
        state: KeyValueState,
        *,
        state_key: str = "window_state",
    ) -> WindowAssignmentOutcome:
        """Persiste solo el evento nuevo y el índice ligero en `state` (O(1) por evento)."""
        entries = self._load_index_entries(state.get(state_key))
        run_user_key = (event.run_id, event.u)
        student_state = entries.get(run_user_key)
        if student_state is None:
            student_state = _StudentRunState(watermark=event.t)
            entries[run_user_key] = student_state

        prev_watermark = student_state.watermark
        dropped_late, added_any, saw_duplicate, closing_buckets = self._assign_event_to_state(
            student_state, event
        )

        is_duplicate = saw_duplicate and not added_any
        if is_duplicate and not closing_buckets:
            return WindowAssignmentOutcome(
                dropped_late_granularities=dropped_late,
                is_duplicate=True,
            )

        if added_any:
            state.set(_event_state_key(event.run_id, event.event_id), _dump_event_compact(event))

        closed_windows: list[ClosedWindow] = []
        if closing_buckets:
            needed_ids = {eid for bucket in closing_buckets for eid in bucket.event_ids}
            loaded_events: dict[str, CanonicalEvent] = {}
            if added_any and event.event_id in needed_ids:
                loaded_events[event.event_id] = event
            for eid in needed_ids:
                if eid not in loaded_events:
                    raw_ev = state.get(_event_state_key(event.run_id, eid))
                    if raw_ev is None:
                        raise KeyError(
                            f"Falta evento '{eid}' en el estado de '{event.run_id}'."
                        )
                    loaded_events[eid] = _load_event_compact(raw_ev)

            closed_windows = [bucket.to_closed_window(loaded_events) for bucket in closing_buckets]

            still_referenced = student_state.referenced_event_ids()
            for obsolete_id in needed_ids - still_referenced:
                state.delete(_event_state_key(event.run_id, obsolete_id))

        if added_any or closing_buckets or student_state.watermark != prev_watermark:
            self._save_index_entries(entries, state, state_key=state_key)

        return WindowAssignmentOutcome(
            closed_windows=self._sort_closed_windows(closed_windows),
            dropped_late_granularities=dropped_late,
            is_duplicate=is_duplicate,
        )

    def flush_run_with_state(
        self,
        run_id: str,
        state: KeyValueState,
        *,
        u: str | None = None,
        state_key: str = "window_state",
    ) -> list[ClosedWindow]:
        entries = self._load_index_entries(state.get(state_key))
        matching_keys = [
            key
            for key in entries
            if key[0] == run_id and (u is None or key[1] == u)
        ]
        if not matching_keys:
            return []

        closed_windows: list[ClosedWindow] = []
        for key in matching_keys:
            student_state = entries.pop(key)
            needed_ids = student_state.referenced_event_ids()
            loaded_events: dict[str, CanonicalEvent] = {}
            for eid in needed_ids:
                raw_ev = state.get(_event_state_key(run_id, eid))
                if raw_ev is None:
                    raise KeyError(f"Falta evento '{eid}' al cerrar ventanas de '{run_id}'.")
                loaded_events[eid] = _load_event_compact(raw_ev)
            for bucket in student_state.open_windows.values():
                closed_windows.append(bucket.to_closed_window(loaded_events))
            for eid in needed_ids:
                state.delete(_event_state_key(run_id, eid))

        self._save_index_entries(entries, state, state_key=state_key)
        return self._sort_closed_windows(closed_windows)

    @staticmethod
    def _load_index_entries(
        data: dict[str, Any] | None,
    ) -> dict[tuple[str, str], _StudentRunState]:
        if not data:
            return {}
        return {
            (entry["run_id"], entry["u"]): _StudentRunState.from_dict(entry["state"])
            for entry in data.get("entries", [])
        }

    @staticmethod
    def _save_index_entries(
        entries: dict[tuple[str, str], _StudentRunState],
        state: KeyValueState,
        *,
        state_key: str,
    ) -> None:
        if not entries:
            state.delete(state_key)
            return
        serialized = [
            {"run_id": run_id, "u": user_id, "state": st.to_index_dict()}
            for (run_id, user_id), st in sorted(entries.items())
        ]
        state.set(state_key, {"entries": serialized})

    def open_window_count(self, run_id: str | None = None, u: str | None = None) -> int:
        total = 0
        for (r_id, user_id), state in self._states.items():
            if run_id is not None and r_id != run_id:
                continue
            if u is not None and user_id != u:
                continue
            total += len(state.open_windows)
        return total

    def to_state_dict(self) -> dict[str, Any]:
        entries = [
            {"run_id": run_id, "u": user_id, "state": state.to_full_dict()}
            for (run_id, user_id), state in sorted(self._states.items())
        ]
        return {"entries": entries}

    @classmethod
    def from_state_dict(
        cls,
        data: dict[str, Any] | None,
        config: WindowsConfig,
        *,
        course_start: datetime | None = None,
        course_end: datetime | None = None,
    ) -> MultiGranularityWindowManager:
        manager = cls(config, course_start=course_start, course_end=course_end)
        if not data:
            return manager
        for entry in data.get("entries", []):
            key = (entry["run_id"], entry["u"])
            manager._states[key] = _StudentRunState.from_dict(entry["state"])
        return manager
