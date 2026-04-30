from __future__ import annotations


def summarize_result(metrics: dict) -> dict:
    return {
        "accepted": metrics.get("accepted", False),
        "bdf_parse_success": metrics.get("bdf_parse_success", False),
        "missing_property_count": metrics.get("missing_property_count", 0),
        "missing_material_count": metrics.get("missing_material_count", 0),
    }
