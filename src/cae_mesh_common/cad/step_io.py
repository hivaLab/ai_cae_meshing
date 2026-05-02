from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any


AP242_SCHEMA_TOKEN = "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF"
FEATURE_SYNTHETIC_TEMPLATES = {
    "plastic_base",
    "ribbed_cover",
    "sheet_metal_box",
    "bracket",
    "screw",
    "motor_dummy",
    "pcb_dummy",
}
CYLINDRICAL_FEATURE_TYPES = {
    "screw_boss",
    "mounting_hole",
    "cylindrical_body",
    "cylindrical_shank",
    "screw_head",
    "shaft",
}


class CadKernelUnavailableError(RuntimeError):
    """Raised when the required local CAD kernel cannot export B-Rep STEP."""


def cad_kernel_status() -> dict[str, object]:
    cadquery_available = importlib.util.find_spec("cadquery") is not None
    ocp_available = importlib.util.find_spec("OCP") is not None
    return {
        "cadquery_available": cadquery_available,
        "ocp_available": ocp_available,
        "kernel": "CadQuery/OCP(OpenCascade)" if cadquery_available and ocp_available else None,
        "step_ap242_brep_export": cadquery_available and ocp_available,
    }


def inspect_step_brep(path: Path | str) -> dict[str, object]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    descriptor_tokens = (
        "procedural placeholder",
        "deterministic procedural geometry descriptor",
    )
    advanced_face_count = text.count("ADVANCED_FACE")
    cylindrical_surface_count = text.count("CYLINDRICAL_SURFACE")
    circle_count = text.count("CIRCLE(")
    closed_shell_count = text.count("CLOSED_SHELL")
    manifold_count = text.count("MANIFOLD_SOLID_BREP")
    product_count = text.count("PRODUCT(")
    return {
        "path": str(path),
        "exists": path.exists(),
        "valid_step": "ISO-10303-21" in text,
        "schema": "AP242" if AP242_SCHEMA_TOKEN in text else "UNKNOWN",
        "is_ap242": AP242_SCHEMA_TOKEN in text,
        "advanced_face_count": advanced_face_count,
        "cylindrical_surface_count": cylindrical_surface_count,
        "circle_count": circle_count,
        "closed_shell_count": closed_shell_count,
        "manifold_solid_brep_count": manifold_count,
        "product_count": product_count,
        "descriptor_only": any(token in text for token in descriptor_tokens) or advanced_face_count == 0,
        "is_brep": advanced_face_count > 0 and (closed_shell_count > 0 or manifold_count > 0),
    }


def validate_feature_bearing_step(path: Path | str, parts: list[dict[str, Any]]) -> dict[str, object]:
    """Validate that a synthetic AP242 STEP contains feature-bearing B-Rep evidence.

    This is intentionally stricter than generic STEP validation: a plain box per
    part is a valid B-Rep, but it is not acceptable synthetic training geometry.
    """

    info = inspect_step_brep(path)
    failures: list[str] = []
    if not info["exists"] or not info["valid_step"] or not info["is_ap242"] or not info["is_brep"]:
        failures.append("step_not_valid_ap242_brep")
    if info["descriptor_only"]:
        failures.append("descriptor_or_non_brep_step")

    unsupported = sorted({_cad_template(part) for part in parts} - FEATURE_SYNTHETIC_TEMPLATES)
    if unsupported:
        failures.append(f"unsupported_feature_synthetic_template:{','.join(unsupported)}")

    box_only_face_limit = 6 * len(parts)
    has_curved_topology = int(info["cylindrical_surface_count"]) > 0 or int(info["circle_count"]) > 0
    if int(info["advanced_face_count"]) <= box_only_face_limit and not has_curved_topology:
        failures.append("box_only_or_underfeatured_face_count")

    feature_types = {
        str(feature.get("feature_type"))
        for part in parts
        for feature in (part.get("features") or [])
        if isinstance(feature, dict)
    }
    if feature_types & CYLINDRICAL_FEATURE_TYPES and int(info["cylindrical_surface_count"]) == 0 and int(info["circle_count"]) == 0:
        failures.append("missing_cylindrical_or_circular_topology_evidence")

    return {
        **info,
        "feature_bearing": not failures,
        "box_only_face_limit": box_only_face_limit,
        "feature_types": sorted(feature_types),
        "failures": failures,
    }


def write_ap242_brep_step(path: Path | str, sample_id: str, parts: list[dict[str, Any]]) -> Path:
    """Export a deterministic synthetic assembly as real AP242 B-Rep STEP."""

    status = cad_kernel_status()
    if not status["step_ap242_brep_export"]:
        raise CadKernelUnavailableError(f"CadQuery/OCP CAD kernel is unavailable: {status}")

    import cadquery as cq
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Controller

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    STEPControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")

    assembly = cq.Assembly(name=_step_name(sample_id))
    placements = _assembly_placements(parts)
    for index, part in enumerate(parts):
        solid = _part_solid(cq, part)
        x, y, z = placements[index]
        part_name = _step_name(str(part.get("part_uid") or part.get("name") or f"part_{index:02d}"))
        assembly.add(solid, name=part_name, loc=cq.Location(cq.Vector(x, y, z)))

    assembly.save(str(path), exportType="STEP")
    info = validate_feature_bearing_step(path, parts)
    if not info["feature_bearing"]:
        raise RuntimeError(f"feature-bearing AP242 B-Rep STEP export failed validation: {info}")
    return path


def assembly_part_placements(parts: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
    """Return the deterministic assembly placements used for AP242 export."""

    return _assembly_placements(parts)


def assembly_part_boxes(parts: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Return deterministic part bounding boxes in assembly coordinates."""

    boxes: list[dict[str, object]] = []
    for part, placement in zip(parts, _assembly_placements(parts)):
        dims = part.get("dimensions") or {}
        length = _positive_float(dims.get("length"), "length", part)
        width = _positive_float(dims.get("width"), "width", part)
        height = _positive_float(dims.get("height"), "height", part)
        x, y, z = placement
        boxes.append(
            {
                "part_uid": part.get("part_uid"),
                "origin": [x, y, z],
                "dimensions": [length, width, height],
                "center": [x + length / 2.0, y + width / 2.0, z + height / 2.0],
            }
        )
    return boxes


def _part_solid(cq: Any, part: dict[str, Any]) -> Any:
    dims = part.get("dimensions") or {}
    length = _positive_float(dims.get("length"), "length", part)
    width = _positive_float(dims.get("width"), "width", part)
    height = _positive_float(dims.get("height"), "height", part)
    template = _cad_template(part)
    builders = {
        "plastic_base": _plastic_base_solid,
        "ribbed_cover": _ribbed_cover_solid,
        "sheet_metal_box": _sheet_metal_box_solid,
        "bracket": _bracket_solid,
        "pcb_dummy": _pcb_dummy_solid,
        "motor_dummy": _motor_dummy_solid,
        "screw": _screw_solid,
    }
    builder = builders.get(template)
    if builder is None:
        raise ValueError(f"no feature-bearing CAD builder for template {template!r} in part {part.get('part_uid')!r}")
    try:
        return builder(cq, length, width, height, part)
    except Exception as exc:
        raise RuntimeError(f"feature-bearing CAD build failed for part {part.get('part_uid')!r} template {template!r}") from exc


def _cad_template(part: dict[str, Any]) -> str:
    explicit = part.get("cad_template")
    if explicit:
        return str(explicit)
    name = str(part.get("name") or "")
    for template in sorted(FEATURE_SYNTHETIC_TEMPLATES, key=len, reverse=True):
        if name == template or name.startswith(f"{template}_"):
            return template
    return name


def _plastic_base_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    thickness = _thickness(part, default=2.2)
    wall = max(thickness * 1.4, 3.0)
    boss_radius = max(min(length, width) * 0.045, 5.0)
    boss_height = max(height * 0.72, thickness * 4.0)
    solid = _box(cq, length, width, thickness)
    solid = _union_all(
        solid,
        [
            _box(cq, length, wall, height - thickness, 0.0, 0.0, thickness),
            _box(cq, length, wall, height - thickness, 0.0, width - wall, thickness),
            _box(cq, wall, width, height - thickness, 0.0, 0.0, thickness),
            _box(cq, wall, width, height - thickness, length - wall, 0.0, thickness),
        ],
    )
    for x, y in _corner_points(length, width, 0.16, 0.18):
        solid = solid.union(_cylinder_z(cq, boss_radius, boss_height, x, y, thickness))
    for index, y in enumerate((width * 0.36, width * 0.5, width * 0.64)):
        x_offset = length * (0.18 + 0.04 * index)
        solid = solid.union(_box(cq, length * 0.64, max(thickness, 2.4), max(height * 0.34, 6.0), x_offset, y, thickness))
    for x, y in _corner_points(length, width, 0.16, 0.18):
        solid = solid.cut(_cylinder_z(cq, boss_radius * 0.42, height + 4.0, x, y, -2.0))
    return solid


def _ribbed_cover_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    thickness = _thickness(part, default=2.0)
    lip = max(thickness * 1.5, 3.0)
    plate_z = max(height - thickness, thickness)
    solid = _box(cq, length, width, thickness, 0.0, 0.0, plate_z)
    solid = _union_all(
        solid,
        [
            _box(cq, length, lip, plate_z, 0.0, 0.0, 0.0),
            _box(cq, length, lip, plate_z, 0.0, width - lip, 0.0),
            _box(cq, lip, width, plate_z, 0.0, 0.0, 0.0),
            _box(cq, lip, width, plate_z, length - lip, 0.0, 0.0),
        ],
    )
    rib_height = max(height * 0.4, 4.0)
    for y in (width * 0.28, width * 0.42, width * 0.58, width * 0.72):
        solid = solid.union(_box(cq, length * 0.72, max(thickness * 0.9, 1.8), rib_height, length * 0.14, y, plate_z - rib_height))
    hole_radius = max(min(length, width) * 0.018, 2.0)
    for x, y in _corner_points(length, width, 0.12, 0.16):
        solid = solid.cut(_cylinder_z(cq, hole_radius, height + 4.0, x, y, -2.0))
    return solid


def _sheet_metal_box_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    thickness = _thickness(part, default=1.0)
    wall = max(thickness * 2.0, 2.2)
    flange = max(min(width, length) * 0.08, 8.0)
    solid = _box(cq, length, width, thickness)
    solid = _union_all(
        solid,
        [
            _box(cq, length, wall, height, 0.0, 0.0, 0.0),
            _box(cq, length, wall, height, 0.0, width - wall, 0.0),
            _box(cq, wall, width, height, 0.0, 0.0, 0.0),
            _box(cq, wall, width, height, length - wall, 0.0, 0.0),
            _box(cq, length, flange, thickness, 0.0, -flange, height),
            _box(cq, length, flange, thickness, 0.0, width, height),
        ],
    )
    hole_radius = max(min(length, width) * 0.02, 2.4)
    for x, y in _corner_points(length, width, 0.18, 0.18):
        solid = solid.cut(_cylinder_z(cq, hole_radius, height + 6.0, x, y, -3.0))
    return solid


def _bracket_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    thickness = _thickness(part, default=1.2)
    solid = _box(cq, length, width, thickness)
    solid = solid.union(_box(cq, length, thickness * 1.6, height, 0.0, width - thickness * 1.6, 0.0))
    solid = solid.union(_box(cq, thickness * 1.6, width, height * 0.55, 0.0, 0.0, 0.0))
    hole_radius = max(min(length, width) * 0.045, 2.5)
    for x, y in _corner_points(length, width, 0.24, 0.25):
        solid = solid.cut(_cylinder_z(cq, hole_radius, height + 4.0, x, y, -2.0))
    return solid


def _pcb_dummy_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    solid = _box(cq, length, width, height)
    hole_radius = max(min(length, width) * 0.025, 1.5)
    for x, y in _corner_points(length, width, 0.12, 0.14):
        solid = solid.cut(_cylinder_z(cq, hole_radius, height + 2.0, x, y, -1.0))
    return solid


def _motor_dummy_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    radius = min(length, width) / 2.0
    center_x = length / 2.0
    center_y = width / 2.0
    solid = _cylinder_z(cq, radius, height, center_x, center_y, 0.0)
    solid = solid.union(_cylinder_z(cq, radius * 0.72, max(height * 0.08, 5.0), center_x, center_y, height))
    solid = solid.union(_cylinder_z(cq, max(radius * 0.16, 3.0), max(height * 0.16, 8.0), center_x, center_y, height + max(height * 0.08, 5.0)))
    return solid


def _screw_solid(cq: Any, length: float, width: float, height: float, part: dict[str, Any]) -> Any:
    head_radius = min(length, width) / 2.0
    head_height = min(max(head_radius * 0.55, 2.2), height * 0.28)
    shank_radius = max(head_radius * 0.34, 1.6)
    center_x = length / 2.0
    center_y = width / 2.0
    shank_height = max(height - head_height, head_height)
    solid = _cylinder_z(cq, shank_radius, shank_height, center_x, center_y, 0.0)
    solid = solid.union(_cylinder_z(cq, head_radius, head_height, center_x, center_y, shank_height))
    return solid


def _box(cq: Any, length: float, width: float, height: float, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Any:
    return cq.Workplane("XY").box(length, width, height, centered=(False, False, False)).translate((x, y, z))


def _cylinder_z(cq: Any, radius: float, height: float, x: float, y: float, z: float) -> Any:
    return cq.Workplane("XY").center(x, y).circle(radius).extrude(height).translate((0.0, 0.0, z))


def _union_all(base: Any, solids: list[Any]) -> Any:
    result = base
    for solid in solids:
        result = result.union(solid)
    return result


def _corner_points(length: float, width: float, x_frac: float, y_frac: float) -> list[tuple[float, float]]:
    return [
        (length * x_frac, width * y_frac),
        (length * (1.0 - x_frac), width * y_frac),
        (length * x_frac, width * (1.0 - y_frac)),
        (length * (1.0 - x_frac), width * (1.0 - y_frac)),
    ]


def _thickness(part: dict[str, Any], default: float) -> float:
    value = part.get("nominal_thickness")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _assembly_placements(parts: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
    placements: list[tuple[float, float, float]] = []
    x_cursor = 0.0
    y_cursor = 0.0
    row_height = 0.0
    row_limit = 900.0
    gap = 30.0
    for part in parts:
        dims = part.get("dimensions") or {}
        length = _positive_float(dims.get("length"), "length", part)
        width = _positive_float(dims.get("width"), "width", part)
        if x_cursor > 0 and x_cursor + length > row_limit:
            x_cursor = 0.0
            y_cursor += row_height + gap
            row_height = 0.0
        placements.append((x_cursor, y_cursor, 0.0))
        x_cursor += length + gap
        row_height = max(row_height, width)
    return placements


def _positive_float(value: object, field: str, part: dict[str, Any]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"part {part.get('part_uid')} has invalid {field}: {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"part {part.get('part_uid')} has non-positive {field}: {parsed}")
    return parsed


def _step_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned or "entity"
