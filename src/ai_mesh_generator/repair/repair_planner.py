from __future__ import annotations


def plan_repairs(metrics: dict) -> list[dict]:
    if metrics.get("accepted", False):
        return []
    return [{"action": "local_remesh", "reason": reason} for reason in metrics.get("failed_regions", [])]
