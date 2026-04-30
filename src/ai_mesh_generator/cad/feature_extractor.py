from __future__ import annotations


def extract_features(assembly: dict) -> dict:
    assembly = dict(assembly)
    assembly["feature_summary"] = {
        "part_count": len(assembly.get("parts", [])),
        "connection_count": len(assembly.get("connections", [])),
        "defect_count": len(assembly.get("defects", [])),
    }
    return assembly
