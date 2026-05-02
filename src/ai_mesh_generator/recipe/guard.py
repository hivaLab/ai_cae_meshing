from __future__ import annotations


def apply_recipe_guard(prediction: dict, assembly: dict, min_confidence: float = 0.55) -> dict:
    manual_review = []
    parts_by_uid = {part["part_uid"]: part for part in assembly.get("parts", [])}
    strategy_by_uid = {
        item.get("part_uid"): str(item.get("strategy", "")).lower()
        for item in prediction.get("part_strategies", [])
    }
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
    guarded_size_fields = []
    for item in prediction["size_fields"]:
        item = dict(item)
        part_uid = item["part_uid"]
        part = parts_by_uid.get(part_uid, {})
        template = str(part.get("cad_template") or part.get("name") or "")
        strategy = strategy_by_uid.get(part_uid, str(part.get("strategy", "")).lower())
        minimum = 4.0 if "screw" in template else 3.5 if strategy in {"solid", "solid_tet"} else 0.0
        if minimum and float(item.get("target_size", 0.0)) < minimum:
            item["guard_adjustment"] = "minimum_feature_solid_size"
            item["pre_guard_target_size"] = item.get("target_size")
            item["target_size"] = minimum
        guarded_size_fields.append(item)
    guarded_connections = []
    for connection in prediction.get("connections", []):
        connection = dict(connection)
        if connection.get("preserve_hole", False):
            connection["delete_hole_allowed"] = False
        guarded_connections.append(connection)
    return {
        "part_strategies": guarded_part_strategies,
        "size_fields": guarded_size_fields,
        "connections": guarded_connections,
        "guard": {
            "min_confidence": min_confidence,
            "manual_review": manual_review,
            "named_boundary_preservation": sorted(named_parts),
            "connection_hole_preservation": True,
        },
    }
