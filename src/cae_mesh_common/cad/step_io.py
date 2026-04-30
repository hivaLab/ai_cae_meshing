from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any


AP242_SCHEMA_TOKEN = "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF"


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
        "closed_shell_count": closed_shell_count,
        "manifold_solid_brep_count": manifold_count,
        "product_count": product_count,
        "descriptor_only": any(token in text for token in descriptor_tokens) or advanced_face_count == 0,
        "is_brep": advanced_face_count > 0 and (closed_shell_count > 0 or manifold_count > 0),
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
    info = inspect_step_brep(path)
    if not info["valid_step"] or not info["is_ap242"] or not info["is_brep"] or info["descriptor_only"]:
        raise RuntimeError(f"AP242 B-Rep STEP export failed validation: {info}")
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
    return cq.Workplane("XY").box(length, width, height, centered=(False, False, False))


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
