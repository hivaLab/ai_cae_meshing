"""Pure sizing formulas for CDF AMG-compatible labels."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def clamp(value: float, minimum: float, maximum: float) -> float:
    if minimum > maximum:
        raise ValueError("minimum must be <= maximum")
    return max(minimum, min(maximum, value))


def safe_ceil(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("value must be finite")
    return int(math.ceil(value))


def make_even(value: int) -> int:
    if value < 0:
        raise ValueError("value must be non-negative")
    return value if value % 2 == 0 else value + 1


def h0_from_midsurface_area(area_mid_mm2: float) -> float:
    if area_mid_mm2 <= 0:
        raise ValueError("area_mid_mm2 must be positive")
    return clamp(0.035 * math.sqrt(area_mid_mm2), 3.0, 6.0)


def length_bounds_from_h0(h0_mm: float) -> tuple[float, float]:
    if h0_mm <= 0:
        raise ValueError("h0_mm must be positive")
    return 0.30 * h0_mm, 1.80 * h0_mm


def chord_error_size(
    radius_mm: float,
    thickness_mm: float,
    h0_mm: float,
    h_min_mm: float | None = None,
    h_max_mm: float | None = None,
) -> float:
    if radius_mm <= 0 or thickness_mm <= 0 or h0_mm <= 0:
        raise ValueError("radius_mm, thickness_mm, and h0_mm must be positive")
    delta_max = min(0.05 * thickness_mm, 0.02 * h0_mm)
    size = math.sqrt(8.0 * radius_mm * delta_max)
    if h_min_mm is None:
        h_min_mm = 0.0
    if h_max_mm is None:
        h_max_mm = h0_mm
    return clamp(size, h_min_mm, h_max_mm)


def smooth_log_sizes(
    raw_h: Sequence[float],
    adjacency: Iterable[tuple[int, int]],
    h_min: float,
    h_max: float,
    g_max: float,
    num_iter: int = 20,
) -> list[float]:
    if h_min <= 0 or h_max <= 0 or g_max <= 1:
        raise ValueError("h_min/h_max must be positive and g_max must be > 1")
    if h_min > h_max:
        raise ValueError("h_min must be <= h_max")
    h = [clamp(float(value), h_min, h_max) for value in raw_h]
    edges = list(adjacency)
    for _ in range(num_iter):
        for i, j in edges:
            if h[i] > h[j] * g_max:
                h[i] = h[j] * g_max
            elif h[j] > h[i] * g_max:
                h[j] = h[i] * g_max
        h = [clamp(value, h_min, h_max) for value in h]
    return h
