from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class LatencySummary:
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    mean_ms: float | None


def summarize_latencies_ms(values_ms: Sequence[float]) -> LatencySummary:
    if not values_ms:
        return LatencySummary(p50_ms=None, p95_ms=None, p99_ms=None, mean_ms=None)
    arr = np.asarray(values_ms, dtype=float)
    return LatencySummary(
        p50_ms=round(float(np.percentile(arr, 50)), 4),
        p95_ms=round(float(np.percentile(arr, 95)), 4),
        p99_ms=round(float(np.percentile(arr, 99)), 4),
        mean_ms=round(float(np.mean(arr)), 4),
    )


def compute_throughput_eps(events_count: int, elapsed_sec: float) -> float:
    if events_count <= 0 or elapsed_sec <= 0:
        return 0.0
    return round(events_count / elapsed_sec, 4)
