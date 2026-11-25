from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TransitionResult:
    previous_cluster_id: int | None
    transition_detected: bool


@dataclass(slots=True)
class _StudentClusterState:
    last_window_start: datetime
    last_window_id: str
    last_cluster_id: int
    prev_cluster_id_for_last_window: int | None


class TransitionTracker:
    """Rastrea transiciones de clúster por estudiante entre ventanas consecutivas en O(1)."""

    def __init__(self) -> None:
        self._states: dict[str, _StudentClusterState] = {}

    def record(
        self,
        *,
        student_id: str,
        window_id: str,
        window_start: datetime,
        cluster_id: int,
    ) -> TransitionResult:
        existing = self._states.get(student_id)
        if existing is None:
            self._states[student_id] = _StudentClusterState(
                last_window_start=window_start,
                last_window_id=window_id,
                last_cluster_id=cluster_id,
                prev_cluster_id_for_last_window=None,
            )
            return TransitionResult(previous_cluster_id=None, transition_detected=False)

        if existing.last_window_id == window_id:
            # Reprocesamiento idempotente de la misma ventana: conserva el clúster previo real.
            prev = existing.prev_cluster_id_for_last_window
            existing.last_cluster_id = cluster_id
            return TransitionResult(
                previous_cluster_id=prev,
                transition_detected=(prev is not None and cluster_id != prev),
            )

        if window_start < existing.last_window_start:
            return TransitionResult(
                previous_cluster_id=existing.prev_cluster_id_for_last_window,
                transition_detected=False,
            )

        prev = existing.last_cluster_id
        self._states[student_id] = _StudentClusterState(
            last_window_start=window_start,
            last_window_id=window_id,
            last_cluster_id=cluster_id,
            prev_cluster_id_for_last_window=prev,
        )
        return TransitionResult(
            previous_cluster_id=prev,
            transition_detected=(cluster_id != prev),
        )
