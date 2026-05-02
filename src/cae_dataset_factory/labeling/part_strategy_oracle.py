from __future__ import annotations


def part_strategy(part: dict) -> str:
    if part.get("strategy") == "mass_only":
        return "mass_only"
    if part.get("strategy") == "solid":
        return "solid"
    if part.get("strategy") == "connector":
        return "connector"
    if part.get("nominal_thickness", 1.0) <= 1.5:
        return "shell"
    return "shell"
