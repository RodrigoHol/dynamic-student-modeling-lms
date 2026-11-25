"""Gestor de ventanas disjuntas simultáneas por tiempo del evento (`t`) y watermark."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from dsm_common.config import WindowsConfig
from dsm_common.schemas import CanonicalEvent
from dsm_core.windowing.boundaries import WindowSpec, compute_window_spec, ensure_utc


@dataclass(slots=True)
class ClosedWindow:
    """Ventana disjunta cerrada lista para cálculo de características y traza."""

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
    """Resultado de ingresar un evento canónico al gestor multiventana."""

    closed_windows: list[ClosedWindow] = field(default_factory=list)
    dropped_late_granularities: list[str] = field(default_factory=list)
    is_duplicate: bool = False


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
    events: list[CanonicalEvent] = field(default_factory=list)
    seen_event_ids: set[str] = field(default_factory=set)

    def add_event(self, event: CanonicalEvent) -> bool:
        if event.event_id in self.seen_event_ids:
            return False
        self.seen_event_ids.add(event.event_id)
        self.events.append(event)
        if not self.fixed_bounds:
            if event.t < self.window_start:
                self.window_start = event.t
            if event.t > self.window_end:
                self.window_end = event.t
        if event.ingested_at > self.last_event_ingested_at:
            self.last_event_ingested_at = event.ingested_at
        return True

    def to_closed_window(self) -> ClosedWindow:
        ordered_events = sorted(self.events, key=lambda ev: ev.t)
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
            "events": [ev.model_dump(mode="json") for ev in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _WindowBucket:
        events = [CanonicalEvent.model_validate(item) for item in data.get("events", [])]
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
            events=events,
            seen_event_ids={ev.event_id for ev in events},
        )


@dataclass(slots=True)
class _StudentRunState:
    watermark: datetime
    open_windows: dict[tuple[str, str], _WindowBucket] = field(default_factory=dict)
    closed_window_keys: set[tuple[str, str]] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "watermark": self.watermark.isoformat(),
            "open_windows": [bucket.to_dict() for bucket in self.open_windows.values()],
            "closed_window_keys": [list(key) for key in sorted(self.closed_window_keys)],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _StudentRunState:
        open_windows: dict[tuple[str, str], _WindowBucket] = {}
        for item in data.get("open_windows", []):
            bucket = _WindowBucket.from_dict(item)
            open_windows[(bucket.granularity, bucket.window_id)] = bucket
        closed_keys = {(pair[0], pair[1]) for pair in data.get("closed_window_keys", [])}
        return cls(
            watermark=ensure_utc(datetime.fromisoformat(data["watermark"])),
            open_windows=open_windows,
            closed_window_keys=closed_keys,
        )


class MultiGranularityWindowManager:
    """Administra ventanas disjuntas simultáneas (`daily`, `weekly`, `monthly`, `course`)."""

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

    def ingest(self, event: CanonicalEvent) -> WindowAssignmentOutcome:
        """Asigna un evento a las granularidades activas y cierra ventanas vencidas por `t`."""
        state_key = (event.run_id, event.u)
        state = self._states.get(state_key)
        if state is None:
            state = _StudentRunState(watermark=event.t)
            self._states[state_key] = state
        elif event.t > state.watermark:
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
            win_key = (spec.granularity, spec.window_id)

            if win_key in state.closed_window_keys:
                dropped_late.append(granularity)
                continue

            if not spec.close_on_eof and state.watermark >= (spec.window_end + self._grace):
                state.closed_window_keys.add(win_key)
                dropped_late.append(granularity)
                continue

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

        closed_windows: list[ClosedWindow] = []
        keys_to_close = [
            win_key
            for win_key, bucket in state.open_windows.items()
            if self._should_close_on_watermark(bucket, state.watermark)
        ]
        for win_key in keys_to_close:
            bucket = state.open_windows.pop(win_key)
            state.closed_window_keys.add(win_key)
            closed_windows.append(bucket.to_closed_window())

        return WindowAssignmentOutcome(
            closed_windows=self._sort_closed_windows(closed_windows),
            dropped_late_granularities=dropped_late,
            is_duplicate=(saw_duplicate and not added_any),
        )

    def flush_run(self, run_id: str, u: str | None = None) -> list[ClosedWindow]:
        """Cierra y libera todas las ventanas abiertas de una corrida (al recibir EOF)."""
        matching_keys = [
            key
            for key in self._states
            if key[0] == run_id and (u is None or key[1] == u)
        ]
        closed_windows: list[ClosedWindow] = []
        for state_key in matching_keys:
            state = self._states.pop(state_key)
            for bucket in state.open_windows.values():
                closed_windows.append(bucket.to_closed_window())
        return self._sort_closed_windows(closed_windows)

    def open_window_count(self, run_id: str | None = None, u: str | None = None) -> int:
        """Devuelve el número de ventanas actualmente abiertas en memoria."""
        total = 0
        for (r_id, user_id), state in self._states.items():
            if run_id is not None and r_id != run_id:
                continue
            if u is not None and user_id != u:
                continue
            total += len(state.open_windows)
        return total

    def to_state_dict(self) -> dict[str, Any]:
        """Serializa el estado completo a un diccionario compatible con JSON/RocksDB."""
        entries = [
            {"run_id": run_id, "u": user_id, "state": state.to_dict()}
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
        """Reconstruye una instancia desde un diccionario serializado previamente."""
        manager = cls(config, course_start=course_start, course_end=course_end)
        if not data:
            return manager
        for entry in data.get("entries", []):
            key = (entry["run_id"], entry["u"])
            manager._states[key] = _StudentRunState.from_dict(entry["state"])
        return manager
