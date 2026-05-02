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
        hint = str(item.get("geometry_hint_strategy", "")).lower()
        predicted = str(item.get("strategy", "")).lower()
        if hint in {"shell", "solid", "solid_tet", "mass_only", "connector"} and predicted != hint:
            item["pre_guard_strategy"] = item.get("strategy")
            item["strategy"] = hint
            item["guard_adjustment"] = "geometry_hint_strategy_preserved"
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
    guarded_refinement_zones = []
    known_targets = _known_refinement_targets(assembly)
    for zone in prediction.get("refinement_zones", []):
        zone = dict(zone)
        target_type = str(zone.get("target_type", ""))
        target_uid = str(zone.get("target_uid", ""))
        if target_type != "feature" and target_uid not in known_targets.get(target_type, set()):
            if zone.get("required", False):
                manual_review.append(
                    {
                        "target_uid": target_uid,
                        "target_type": target_type,
                        "reason": "required_refinement_zone_target_not_found",
                    }
                )
                zone["manual_review"] = True
            else:
                zone["skipped"] = True
                zone["skip_reason"] = "refinement_zone_target_not_found"
        size = max(0.25, float(zone.get("size_mm", zone.get("target_size_mm", 1.0))))
        min_size = max(0.25, float(zone.get("min_size_mm", size * 0.55)))
        max_size = max(size, float(zone.get("max_size_mm", size * 1.75)))
        if size < min_size:
            zone["pre_guard_size_mm"] = size
            size = min_size
            zone["guard_adjustment"] = "min_refinement_size"
        if size > max_size:
            zone["pre_guard_size_mm"] = size
            size = max_size
            zone["guard_adjustment"] = "max_refinement_size"
        zone["size_mm"] = round(size, 4)
        zone["min_size_mm"] = round(min_size, 4)
        zone["max_size_mm"] = round(max_size, 4)
        guarded_refinement_zones.append(zone)
    return {
        "part_strategies": guarded_part_strategies,
        "size_fields": guarded_size_fields,
        "refinement_zones": guarded_refinement_zones,
        "connections": guarded_connections,
        "guard": {
            "min_confidence": min_confidence,
            "manual_review": manual_review,
            "named_boundary_preservation": sorted(named_parts),
            "connection_hole_preservation": True,
            "refinement_zone_count": len(guarded_refinement_zones),
            "required_refinement_zone_count": sum(1 for zone in guarded_refinement_zones if zone.get("required", False)),
        },
    }


def _known_refinement_targets(assembly: dict) -> dict[str, set[str]]:
    targets = {
        "part": set(),
        "face": set(),
        "edge": set(),
        "feature": set(),
        "connection": set(),
        "contact_candidate": set(),
    }
    for part in assembly.get("parts", []):
        targets["part"].add(str(part["part_uid"]))
        for face in part.get("face_signatures", []):
            targets["face"].add(str(face["face_uid"]))
        for feature in part.get("features", []):
            targets["feature"].add(str(feature["feature_uid"]))
        for edge in part.get("topology_edges", []):
            targets["edge"].add(str(edge.get("edge_uid") or edge.get("uid")))
        for local in [
            "x_y0_z0",
            "x_yw_z0",
            "x_y0_zh",
            "x_yw_zh",
            "y_x0_z0",
            "y_xl_z0",
            "y_x0_zh",
            "y_xl_zh",
            "z_x0_y0",
            "z_xl_y0",
            "z_x0_yw",
            "z_xl_yw",
        ]:
            targets["edge"].add(f"{part['part_uid']}_edge_{local}")
    for connection in assembly.get("connections", []):
        uid = str(connection["connection_uid"])
        targets["connection"].add(uid)
        targets["contact_candidate"].add(f"contact_{uid}")
    return targets
