from __future__ import annotations


def apply_recipe_guard(prediction: dict, assembly: dict, min_confidence: float = 0.55) -> dict:
    manual_review = []
    named_parts = set()
    for values in assembly.get("boundary_named_sets", {}).values():
        for value in values:
            if isinstance(value, dict):
                named_parts.add(value.get("part_uid", ""))
            else:
                named_parts.add(value)
    named_parts.discard("")
    guarded_part_strategies = []
    for item in prediction["part_strategies"]:
        item = dict(item)
        if item["part_uid"] in named_parts:
            item["preserve_named_boundary"] = True
            item["defeature_allowed"] = False
        if float(item.get("confidence", 0.0)) < min_confidence:
            item["manual_review"] = True
            manual_review.append({"target_uid": item["part_uid"], "reason": "low_confidence"})
        guarded_part_strategies.append(item)
    guarded_connections = []
    for connection in prediction.get("connections", []):
        connection = dict(connection)
        if connection.get("preserve_hole", False):
            connection["delete_hole_allowed"] = False
        guarded_connections.append(connection)
    return {
        "part_strategies": guarded_part_strategies,
        "size_fields": prediction["size_fields"],
        "connections": guarded_connections,
        "guard": {
            "min_confidence": min_confidence,
            "manual_review": manual_review,
            "named_boundary_preservation": sorted(named_parts),
            "connection_hole_preservation": True,
        },
    }
