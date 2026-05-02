from __future__ import annotations


def size_for_part(part: dict, defect_count: int) -> float:
    base = max(2.5, min(part["dimensions"]["length"], part["dimensions"]["width"]) / 12.0)
    template = str(part.get("cad_template") or part.get("name") or "")
    if "screw" in template:
        base = max(base, 4.0)
    elif str(part.get("strategy", "")).lower() in {"solid", "solid_tet"}:
        base = max(base, 3.5)
    if defect_count:
        base *= 0.85
    return round(base, 4)
