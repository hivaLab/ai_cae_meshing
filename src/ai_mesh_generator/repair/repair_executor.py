from __future__ import annotations


def execute_repairs(recipe: dict, repairs: list[dict]) -> dict:
    updated = dict(recipe)
    updated.setdefault("guard", {})["repair_attempts"] = repairs
    return updated
