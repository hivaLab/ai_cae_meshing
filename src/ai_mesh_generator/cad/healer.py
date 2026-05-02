from __future__ import annotations


def heal_geometry(assembly: dict) -> dict:
    assembly = dict(assembly)
    assembly["healing"] = {
        "status": "not_performed",
        "operations": [],
        "requires_manual_review": True,
        "reason": "No production CAD healing kernel has modified this geometry in the current workflow.",
    }
    return assembly
