from __future__ import annotations

import math

import pytest

from cad_dataset_factory.cdf.labels.sizing import (
    chord_error_size,
    clamp,
    h0_from_midsurface_area,
    make_even,
    safe_ceil,
    smooth_log_sizes,
)


def test_make_even() -> None:
    assert make_even(12) == 12
    assert make_even(13) == 14
    with pytest.raises(ValueError):
        make_even(-1)


def test_clamp() -> None:
    assert clamp(5.0, 1.0, 10.0) == 5.0
    assert clamp(-1.0, 1.0, 10.0) == 1.0
    assert clamp(11.0, 1.0, 10.0) == 10.0


def test_safe_ceil() -> None:
    assert safe_ceil(1.01) == 2
    with pytest.raises(ValueError):
        safe_ceil(math.inf)


def test_h0_formula() -> None:
    assert h0_from_midsurface_area(16000.0) == pytest.approx(0.035 * math.sqrt(16000.0))
    assert h0_from_midsurface_area(100.0) == 3.0


def test_chord_error_formula() -> None:
    assert chord_error_size(10.0, 1.0, 4.0, 0.1, 4.0) == pytest.approx(2.0)


def test_smooth_log_sizes_bounds() -> None:
    result = smooth_log_sizes([0.1, 20.0], [(0, 1)], 1.0, 10.0, 1.3)
    assert all(1.0 <= value <= 10.0 for value in result)


def test_smooth_log_sizes_growth_rate() -> None:
    result = smooth_log_sizes([1.0, 10.0, 10.0], [(0, 1), (1, 2)], 1.0, 10.0, 1.3)
    for i, j in [(0, 1), (1, 2)]:
        ratio = max(result[i], result[j]) / min(result[i], result[j])
        assert ratio <= 1.3 + 1e-9
