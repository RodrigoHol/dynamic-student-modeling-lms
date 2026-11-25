"""Cálculo de límites de ventanas temporales disjuntas basadas en `t` (ADR-12)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dsm_common.config import WindowDefinition


def ensure_utc(value: datetime) -> datetime:
    """Normaliza una marca temporal a UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """Especificación de una ventana disjunta calculada desde `t`."""

    granularity: str
    window_id: str
    window_start: datetime
    window_end: datetime
    close_on_eof: bool = False
    fixed_bounds: bool = True


def compute_window_spec(
    t: datetime,
    granularity: str,
    definition: WindowDefinition,
    *,
    course_id: str,
    course_start: datetime | None = None,
    course_end: datetime | None = None,
) -> WindowSpec:
    """Asigna una marca temporal `t` a su ventana disjunta en la granularidad dada."""
    ts = ensure_utc(t)

    if granularity == "daily":
        duration_sec = definition.duration_seconds or 86400
        if duration_sec == 86400:
            start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            return WindowSpec(
                granularity=granularity,
                window_id=start.strftime("%Y-%m-%d"),
                window_start=start,
                window_end=end,
                close_on_eof=bool(definition.close_on_eof),
                fixed_bounds=True,
            )

    if granularity == "weekly":
        duration_sec = definition.duration_seconds or 604800
        if duration_sec == 604800:
            iso_year, iso_week, iso_weekday = ts.isocalendar()
            start = (ts - timedelta(days=iso_weekday - 1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
            return WindowSpec(
                granularity=granularity,
                window_id=f"{iso_year:04d}-W{iso_week:02d}",
                window_start=start,
                window_end=end,
                close_on_eof=bool(definition.close_on_eof),
                fixed_bounds=True,
            )

    if granularity == "monthly":
        if definition.mode == "fixed_30d":
            duration_sec = definition.duration_seconds or 2592000
            anchor = (
                ensure_utc(course_start)
                if course_start is not None
                else datetime(1970, 1, 1, tzinfo=UTC)
            )
            block_idx = math.floor((ts - anchor).total_seconds() / duration_sec)
            start = anchor + timedelta(seconds=block_idx * duration_sec)
            end = start + timedelta(seconds=duration_sec)
            return WindowSpec(
                granularity=granularity,
                window_id=f"M{block_idx + 1:02d}_{start.strftime('%Y-%m-%d')}",
                window_start=start,
                window_end=end,
                close_on_eof=bool(definition.close_on_eof),
                fixed_bounds=True,
            )

        start = ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return WindowSpec(
            granularity=granularity,
            window_id=f"{start.year:04d}-{start.month:02d}",
            window_start=start,
            window_end=end,
            close_on_eof=bool(definition.close_on_eof),
            fixed_bounds=True,
        )

    if granularity == "course" or definition.mode == "full_course":
        close_on_eof = True if definition.close_on_eof is None else bool(definition.close_on_eof)
        has_fixed_bounds = course_start is not None and course_end is not None
        start = ensure_utc(course_start) if course_start is not None else ts
        end = ensure_utc(course_end) if course_end is not None else ts
        return WindowSpec(
            granularity=granularity,
            window_id=course_id,
            window_start=start,
            window_end=end,
            close_on_eof=close_on_eof,
            fixed_bounds=has_fixed_bounds,
        )

    duration_sec = definition.duration_seconds
    if not duration_sec or duration_sec <= 0:
        raise ValueError(f"Definición de ventana inválida para '{granularity}'.")

    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    bucket_idx = math.floor((ts - epoch).total_seconds() / duration_sec)
    start = epoch + timedelta(seconds=bucket_idx * duration_sec)
    end = start + timedelta(seconds=duration_sec)
    return WindowSpec(
        granularity=granularity,
        window_id=f"{granularity}_{start.strftime('%Y%m%dT%H%M%SZ')}",
        window_start=start,
        window_end=end,
        close_on_eof=bool(definition.close_on_eof),
        fixed_bounds=True,
    )
