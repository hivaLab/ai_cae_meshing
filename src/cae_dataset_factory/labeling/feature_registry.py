from __future__ import annotations


def build_feature_registry(assembly: dict) -> list[dict]:
    records: list[dict] = []
    for part in assembly["parts"]:
        records.extend(part.get("features", []))
    return records
