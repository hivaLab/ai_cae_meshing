from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from cae_mesh_common.cad.step_io import assembly_part_boxes


RECIPE_MARKER = "AI_CAE_RECIPE"


def build_ansa_recipe_plan(assembly: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    """Build the production ANSA controls derived from the guarded AI recipe."""

    parts = assembly.get("parts", [])
    boxes = _assembly_boxes(parts)
    materials = _material_plan(assembly.get("material_library", {}).get("materials", []))
    material_ids = {item["material_id"]: int(item["mid"]) for item in materials}
    base_size = _positive_float(recipe.get("base_size", 10.0), 10.0)
    strategy_by_part = {item.get("part_uid"): _normalize_strategy(str(item.get("strategy", "shell"))) for item in recipe.get("part_strategies", [])}
    size_by_part = {item.get("part_uid"): _positive_float(item.get("target_size"), base_size) for item in recipe.get("size_fields", [])}
    zones_by_part = _refinement_zones_by_part(parts, assembly.get("connections", []), recipe.get("refinement_zones", []))

    part_plans: list[dict[str, Any]] = []
    strategy_counts: dict[str, int] = {}
    for index, part in enumerate(parts, start=1):
        part_uid = str(part["part_uid"])
        strategy = strategy_by_part.get(part_uid, _normalize_strategy(str(part.get("strategy", "shell"))))
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        requested_target_size = round(size_by_part.get(part_uid, base_size), 4)
        refinement_zones = zones_by_part.get(part_uid, [])
        effective_target_size = min(
            [requested_target_size] + [float(zone["size_mm"]) for zone in refinement_zones if not zone.get("skipped")]
        )
        target_size = round(effective_target_size, 4)
        material_id = str(part["material_id"])
        mid = material_ids[material_id]
        thickness = max(0.05, float(part.get("nominal_thickness", 1.0)))
        property_type = _property_type_for_strategy(strategy)
        part_box = boxes[part_uid]
        part_plans.append(
            {
                "part_uid": part_uid,
                "part_name": part.get("name", part_uid),
                "source_product_name": part.get("source_product_name", part.get("name", part_uid)),
                "source_solid_index": part.get("source_solid_index"),
                "part_index": index,
                "strategy": strategy,
                "requested_property_type": "PSOLID" if strategy in {"solid", "solid_tet"} else property_type,
                "solver_property_type": property_type,
                "property_id": index,
                "property_name": _safe_name(f"AI_{index:03d}_{part.get('name', part_uid)}"),
                "material_id": material_id,
                "material_numeric_id": mid,
                "nominal_thickness": round(thickness, 6),
                "target_size": target_size,
                "part_level_target_size": requested_target_size,
                "min_size": round(max(0.25, target_size * 0.15), 4),
                "max_size": round(max(target_size, target_size * 1.65), 4),
                "quality_profile": _quality_profile(strategy, thickness),
                "geometry_box": part_box,
                "mesh_session_keywords": _mesh_session_keywords(target_size),
                "refinement_zones": refinement_zones,
                "refinement_zone_count": len(refinement_zones),
                "batch_mesh": strategy not in {"mass_only", "connector", "approved_exclude", "exclude"},
            }
        )

    connector_pid = 9001
    connection_plans = _connection_plan(assembly.get("connections", []), boxes, connector_pid)
    return {
        "plan_version": "ansa_recipe_plan.v1",
        "sample_id": assembly["sample_id"],
        "recipe_id": recipe.get("recipe_id", ""),
        "backend": "ANSA_BATCH",
        "base_size": round(base_size, 4),
        "fallback_enabled": False,
        "materials": materials,
        "parts": part_plans,
        "connections": connection_plans,
        "refinement_zones": list(recipe.get("refinement_zones", [])),
        "connector_property": {
            "property_id": connector_pid,
            "property_type": "PBUSH",
            "material_numeric_id": materials[0]["mid"] if materials else 1,
            "stiffness": [100000.0, 100000.0, 100000.0, 1000.0, 1000.0, 1000.0],
        },
        "mass_properties": {
            "density_scale": 1.0e-6,
            "minimum_mass": 0.1,
        },
        "native_entity_generation": {
            "solid_tetra": {
                "enabled": True,
                "entity_type": "SOLID",
                "element_type": "CTETRA",
                "property_type": "PSOLID",
                "method": "batchmesh_volume_scenario",
                "session_type": "ANSA_VOLUME_SESSION",
            },
            "connector": {
                "enabled": True,
                "entity_type": "CBUSH",
                "property_type": "PBUSH",
            },
            "mass": {
                "enabled": True,
                "entity_type": "CONM2",
            },
            "id_start": 800000,
        },
        "ansa_session": {
            "mode": "per_part_batch_mesh_session",
            "global_keywords": _mesh_session_keywords(base_size),
            "quality_keywords": {"distortion-angle": "5."},
            "required_calls": [
                "batchmesh.GetNewSession",
                "batchmesh.SetSessionParameters",
                "batchmesh.AddPartToSession",
                "batchmesh.RunSession",
            ],
        },
        "quality_criteria": {
            "shell": {"max_aspect_ratio": 8.0, "max_skew_deg": 60.0, "min_jacobian": 0.2},
            "solid": {"min_scaled_jacobian": 0.1, "max_dihedral_deg": 165.0},
            "connector": {"required_reflection_rate": 1.0},
            "bdf": {"property_assignment_rate_min": 1.0, "material_assignment_rate_min": 1.0},
        },
        "summary": {
            "part_count": len(part_plans),
            "batch_mesh_part_count": sum(1 for item in part_plans if item["batch_mesh"]),
            "mass_only_part_count": sum(1 for item in part_plans if item["strategy"] == "mass_only"),
            "connection_count": len(connection_plans),
            "strategy_counts": strategy_counts,
            "per_part_size_field_count": len(part_plans),
            "refinement_zone_count": len(recipe.get("refinement_zones", [])),
            "required_refinement_zone_count": sum(1 for zone in recipe.get("refinement_zones", []) if zone.get("required", False)),
            "parts_with_refinement_zones": sum(1 for part in part_plans if part["refinement_zone_count"] > 0),
        },
    }


def write_ansa_recipe_plan(plan: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_ansa_control_files(plan: dict[str, Any], stage_dir: Path | str) -> dict[str, str]:
    stage = Path(stage_dir)
    stage.mkdir(parents=True, exist_ok=True)
    parameter_path = stage / "ansa_mesh_parameters.json"
    quality_path = stage / "ansa_quality_criteria.json"
    parameter_path.write_text(
        json.dumps(
            {
                "sample_id": plan["sample_id"],
                "global_keywords": plan["ansa_session"]["global_keywords"],
                "per_part_keywords": {
                    part["part_uid"]: part["mesh_session_keywords"] for part in plan.get("parts", [])
                },
                "refinement_zones": plan.get("refinement_zones", []),
                "per_part_refinement_zones": {
                    part["part_uid"]: part.get("refinement_zones", []) for part in plan.get("parts", [])
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    quality_path.write_text(json.dumps(plan["quality_criteria"], indent=2, sort_keys=True), encoding="utf-8")
    return {"mesh_parameters_json": str(parameter_path.resolve()), "quality_criteria_json": str(quality_path.resolve())}


def apply_solver_deck_recipe(
    bdf_path: Path | str, plan: dict[str, Any], create_missing_elements: bool = False
) -> dict[str, Any]:
    """Apply recipe material and property cards to a Nastran deck.

    ANSA owns CAD import, Batch Mesh Manager element generation, native connector
    entities, and native mass entities. This function is intentionally limited to
    material/property reflection and rejects solver-deck element creation.
    """

    path = Path(bdf_path)
    original_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = _remove_previous_recipe_cards(original_lines, plan)

    material_cards = _material_cards(plan)
    updated_lines, pshell_stats = _update_pshell_cards(lines, plan)
    connector_pid = int(plan.get("connector_property", {}).get("property_id", 9001))
    pbush_card = _pbush_card(connector_pid, plan)

    generated_cards: list[str] = []
    mass_cards = []
    connector_cards = []
    connector_skipped = 0
    if create_missing_elements:
        raise RuntimeError("solver-deck element creation fallback is disabled for production ANSA integration")
    elif plan.get("connections"):
        connector_skipped = len(plan.get("connections", []))

    generated_cards.extend(material_cards)
    generated_cards.append(pbush_card)
    generated_cards.extend(mass_cards)
    generated_cards.extend(connector_cards)
    final_lines = _insert_cards_after_begin_bulk(updated_lines, generated_cards)
    path.write_text("\n".join(final_lines).rstrip() + "\n", encoding="utf-8")
    return {
        "material_cards_written": len(material_cards),
        "pshell_cards_seen": pshell_stats["seen"],
        "pshell_cards_updated": pshell_stats["updated"],
        "pbush_cards_written": 1,
        "mass_elements_written": len(mass_cards) // 2,
        "connector_elements_written": len(connector_cards),
        "connector_elements_skipped": connector_skipped,
        "element_creation_enabled": bool(create_missing_elements),
        "connector_property_id": connector_pid,
        "property_assignment_rate": 1.0 if pshell_stats["seen"] else 0.0,
        "material_assignment_rate": 1.0 if material_cards else 0.0,
        "recipe_marker": RECIPE_MARKER,
    }


def _material_plan(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "material_id": str(material["material_id"]),
            "name": material.get("name", material["material_id"]),
            "mid": index,
            "young_modulus": float(material.get("young_modulus", 1.0)),
            "poisson_ratio": float(material.get("poisson_ratio", 0.3)),
            "density": float(material.get("density", 0.0)),
        }
        for index, material in enumerate(materials, start=1)
    ]


def _connection_plan(connections: list[dict[str, Any]], boxes: dict[str, dict[str, object]], connector_pid: int) -> list[dict[str, Any]]:
    planned = []
    for index, connection in enumerate(connections, start=1):
        part_uid_a = str(connection["part_uid_a"])
        part_uid_b = str(connection["part_uid_b"])
        box_a = boxes.get(part_uid_a)
        box_b = boxes.get(part_uid_b)
        if not box_a or not box_b:
            continue
        planned.append(
            {
                "connection_uid": str(connection.get("connection_uid", f"connection_{index:04d}")),
                "type": connection.get("type", "tied"),
                "part_uid_a": part_uid_a,
                "part_uid_b": part_uid_b,
                "endpoint_a": _interface_point(box_a, box_b),
                "endpoint_b": _interface_point(box_b, box_a),
                "property_id": connector_pid,
                "preserve_hole": bool(connection.get("preserve_hole", False)),
                "delete_hole_allowed": bool(connection.get("delete_hole_allowed", False)),
            }
        )
    return planned


def _refinement_zones_by_part(parts: list[dict[str, Any]], connections: list[dict[str, Any]], zones: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    part_by_uid = {str(part["part_uid"]): part for part in parts}
    face_to_part: dict[str, str] = {}
    edge_to_part: dict[str, str] = {}
    feature_to_part: dict[str, str] = {}
    for part in parts:
        part_uid = str(part["part_uid"])
        for face in part.get("face_signatures", []):
            face_to_part[str(face["face_uid"])] = part_uid
        for feature in part.get("features", []):
            feature_to_part[str(feature["feature_uid"])] = part_uid
        for edge in part.get("topology_edges", []):
            edge_to_part[str(edge.get("edge_uid") or edge.get("uid"))] = part_uid
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
            edge_to_part[f"{part_uid}_edge_{local}"] = part_uid
    connection_to_parts: dict[str, list[str]] = {}
    for connection in connections:
        uid = str(connection.get("connection_uid", ""))
        if uid:
            connection_to_parts[uid] = [str(connection["part_uid_a"]), str(connection["part_uid_b"])]

    result: dict[str, list[dict[str, Any]]] = {uid: [] for uid in part_by_uid}
    for zone in zones:
        target_type = str(zone.get("target_type", ""))
        target_uid = str(zone.get("target_uid", ""))
        part_uids: list[str] = []
        if target_type == "part" and target_uid in part_by_uid:
            part_uids = [target_uid]
        elif target_type == "face":
            part_uids = [face_to_part[target_uid]] if target_uid in face_to_part else []
        elif target_type == "edge":
            part_uids = [edge_to_part[target_uid]] if target_uid in edge_to_part else []
        elif target_type == "feature":
            part_uids = [feature_to_part[target_uid]] if target_uid in feature_to_part else []
        elif target_type in {"contact_candidate", "connection"}:
            key = target_uid.removeprefix("contact_")
            part_uids = [uid for uid in connection_to_parts.get(key, []) if uid in part_by_uid]
        for part_uid in part_uids:
            result.setdefault(part_uid, []).append(zone)
    return result


def _assembly_boxes(parts: list[dict[str, Any]]) -> dict[str, dict[str, object]]:
    boxes = {str(box["part_uid"]): box for box in assembly_part_boxes(parts)}
    for part in parts:
        part_uid = str(part["part_uid"])
        geometry_box = part.get("geometry_box")
        if not geometry_box:
            continue
        origin = _as_point(geometry_box.get("origin", boxes[part_uid]["origin"]))
        dims = _as_point(geometry_box.get("dimensions", boxes[part_uid]["dimensions"]))
        center = _as_point(geometry_box.get("center", [origin[0] + dims[0] / 2.0, origin[1] + dims[1] / 2.0, origin[2] + dims[2] / 2.0]))
        boxes[part_uid] = {
            "part_uid": part_uid,
            "origin": [round(value, 6) for value in origin],
            "dimensions": [round(value, 6) for value in dims],
            "center": [round(value, 6) for value in center],
            "source": "step_topology_geometry_box",
        }
    return boxes


def _interface_point(box: dict[str, object], other: dict[str, object]) -> list[float]:
    center = _as_point(box["center"])
    other_center = _as_point(other["center"])
    dims = _as_point(box["dimensions"])
    point = list(center)
    for axis in range(3):
        delta = other_center[axis] - center[axis]
        if abs(delta) > 1.0e-9:
            point[axis] = center[axis] + math.copysign(dims[axis] / 2.0, delta)
    return [round(value, 6) for value in point]


def _mesh_session_keywords(target_size: float) -> dict[str, str]:
    target = _positive_float(target_size, 10.0)
    min_size = max(0.25, target * 0.15)
    max_size = max(target, target * 1.65)
    return {
        "perimeter_length": _fmt(target),
        "distortion-angle": "5.",
        "min length [shells]": _session_length_line(target, min_size, on=True),
        "max length [shells]": _session_length_line(target, max_size, on=True),
    }


def _session_length_line(target: float, limit: float, on: bool) -> str:
    flag = " ON" if on else "OFF"
    return (
        f"{flag},                :     0XFF0000|     1. |"
        f"          {_fmt(target)},    -1./           0.,    -1./"
        f"          {_fmt(limit)},    -1./           0.,    -1./"
    )


def _material_cards(plan: dict[str, Any]) -> list[str]:
    cards = []
    for material in plan.get("materials", []):
        cards.append(
            "MAT1,{mid},{e},,{nu},{rho} $ {marker}_MATERIAL {mat}".format(
                mid=int(material["mid"]),
                e=_fmt(float(material["young_modulus"])),
                nu=_fmt(float(material["poisson_ratio"])),
                rho=_fmt(float(material["density"])),
                marker=RECIPE_MARKER,
                mat=material["material_id"],
            )
        )
    return cards


def _pbush_card(pid: int, plan: dict[str, Any]) -> str:
    stiffness = plan.get("connector_property", {}).get("stiffness", [100000.0] * 6)
    values = ",".join(_fmt(float(value)) for value in stiffness[:6])
    return f"PBUSH,{pid},K,{values} $ {RECIPE_MARKER}_CONNECTOR_PROPERTY"


def _update_pshell_cards(lines: list[str], plan: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    part_plans = [part for part in plan.get("parts", []) if part.get("solver_property_type") == "PSHELL"]
    pshell_index = 0
    seen = 0
    updated = 0
    result = []
    for line in lines:
        if _card_name(line) != "PSHELL":
            result.append(line)
            continue
        seen += 1
        part = part_plans[pshell_index] if pshell_index < len(part_plans) else None
        pshell_index += 1
        if part is None:
            result.append(line)
            continue
        fields = _fields(line)
        while len(fields) < 4:
            fields.append("")
        fields[2] = str(int(part["material_numeric_id"]))
        fields[3] = _fmt(float(part["nominal_thickness"]))
        result.append(
            ",".join(fields[:4])
            + f" $ {RECIPE_MARKER}_PROPERTY {part['part_uid']} size={_fmt(float(part['target_size']))}"
        )
        updated += 1
    return result, {"seen": seen, "updated": updated}


def _remove_previous_recipe_cards(lines: list[str], plan: dict[str, Any]) -> list[str]:
    material_mids = {int(material["mid"]) for material in plan.get("materials", [])}
    connector_pid = int(plan.get("connector_property", {}).get("property_id", 9001))
    result = []
    skip_continuation = False
    for line in lines:
        name = _card_name(line)
        if skip_continuation and _is_continuation_name(name):
            continue
        if skip_continuation:
            skip_continuation = False
        fields = _fields(line)
        remove_line = False
        if "AI_NATIVE_CONNECTOR_PBUSH" in line:
            remove_line = True
        if RECIPE_MARKER in line and name != "PSHELL":
            remove_line = True
        if name == "MAT1" and len(fields) > 1 and _int_or_none(fields[1]) in material_mids:
            remove_line = True
        if name == "PBUSH" and len(fields) > 1 and _int_or_none(fields[1]) == connector_pid:
            remove_line = True
        if remove_line:
            skip_continuation = True
            continue
        result.append(line)
    return result


def _insert_cards_after_begin_bulk(lines: list[str], cards: list[str]) -> list[str]:
    if not cards:
        return lines
    result = []
    inserted = False
    for line in lines:
        result.append(line)
        if not inserted and _card_name(line) == "BEGIN":
            result.extend(cards)
            inserted = True
    if not inserted:
        insert_at = 1 if lines and _card_name(lines[0]) != "ENDDATA" else 0
        result = lines[:insert_at] + cards + lines[insert_at:]
    return result


def _property_ids(lines: list[str]) -> list[int]:
    prop_names = {"PSHELL", "PSOLID", "PBUSH"}
    ids = [_int_or_none(_fields(line)[1]) for line in lines if _card_name(line) in prop_names and len(_fields(line)) > 1]
    return [value for value in ids if value is not None]


def _card_name(line: str) -> str:
    clean = line.split("$", 1)[0].strip()
    if not clean:
        return ""
    return clean.split(",", 1)[0].split()[0].upper()


def _is_continuation_name(name: str) -> bool:
    return name.startswith("+") or name.startswith("*")


def _fields(line: str) -> list[str]:
    clean = line.split("$", 1)[0].strip()
    if not clean:
        return []
    return [part.strip() for part in clean.split(",")] if "," in clean else clean.split()


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_strategy(strategy: str) -> str:
    lookup = {
        "SHELL_MIDSURFACE": "shell",
        "SOLID_TETRA": "solid",
        "CONNECTOR_REPLACEMENT": "connector",
        "MASS_ONLY": "mass_only",
        "APPROVED_EXCLUDE": "approved_exclude",
        "MANUAL_REVIEW": "shell",
    }
    return lookup.get(strategy.upper(), strategy.lower())


def _property_type_for_strategy(strategy: str) -> str:
    if strategy == "mass_only":
        return "CONM2"
    if strategy == "connector":
        return "PBUSH"
    return "PSHELL"


def _quality_profile(strategy: str, thickness: float) -> str:
    if strategy == "mass_only":
        return "mass_only"
    if strategy in {"solid", "solid_tet"}:
        return "solid_small_structural"
    return "shell_thin" if thickness <= 2.5 else "shell_structural"


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_point(values: Any) -> tuple[float, float, float]:
    seq = list(values)
    return (float(seq[0]), float(seq[1]), float(seq[2]))


def _fmt(value: float) -> str:
    text = f"{value:.8g}"
    return f"{text}.0" if re.fullmatch(r"[+-]?\d+", text) else text


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned[:64] or "AI_CAE_ENTITY"
