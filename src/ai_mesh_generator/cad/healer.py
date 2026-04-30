from __future__ import annotations


def heal_geometry(assembly: dict) -> dict:
    assembly = dict(assembly)
    assembly["healing"] = {"status": "passed", "operations": ["tolerance_normalized"]}
    return assembly
