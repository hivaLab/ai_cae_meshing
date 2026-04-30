from __future__ import annotations


def size_for_part(part: dict, defect_count: int) -> float:
    base = max(2.5, min(part["dimensions"]["length"], part["dimensions"]["width"]) / 12.0)
    if defect_count:
        base *= 0.85
    return round(base, 4)
