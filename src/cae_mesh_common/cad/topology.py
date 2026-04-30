from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .step_io import CadKernelUnavailableError, cad_kernel_status, inspect_step_brep


DEFAULT_STEP_MATERIAL_LIBRARY = {
    "materials": [
        {
            "material_id": "MAT_STEP_GENERIC",
            "name": "Generic imported STEP material",
            "young_modulus": 210000.0,
            "poisson_ratio": 0.3,
            "density": 7.85e-9,
        }
    ]
}


class StepTopologyError(RuntimeError):
    """Raised when a STEP AP242 B-Rep file cannot be traversed as topology."""


def transform_identity() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def extract_step_assembly_topology(
    step_path: Path | str,
    sample_id: str | None = None,
    material_library: dict[str, Any] | None = None,
    connections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Import a real STEP AP242 B-Rep assembly and return an AMG assembly dict.

    The synthetic CDF path already carries procedural part metadata. This
    function intentionally ignores that path and derives part, face and edge
    topology from the STEP file using CadQuery/OCP.
    """

    path = Path(step_path)
    step_info = inspect_step_brep(path)
    if not step_info["exists"] or not step_info["valid_step"] or not step_info["is_brep"] or step_info["descriptor_only"]:
        raise StepTopologyError(f"STEP file is not a real AP242 B-Rep assembly: {step_info}")
    status = cad_kernel_status()
    if not status["cadquery_available"] or not status["ocp_available"]:
        raise CadKernelUnavailableError(f"CadQuery/OCP CAD kernel is unavailable: {status}")

    from cadquery import importers

    workplane = importers.importStep(str(path))
    solids = list(workplane.solids().vals())
    if not solids:
        raise StepTopologyError(f"STEP file contains no importable solids: {path}")

    sample = _safe_uid(sample_id or path.stem)
    product_names = _step_product_names(path)
    part_names = _part_names_for_solids(product_names, len(solids), sample)
    library = material_library or DEFAULT_STEP_MATERIAL_LIBRARY
    material_ids = [str(item["material_id"]) for item in library.get("materials", [])]
    if not material_ids:
        raise StepTopologyError("material_library must contain at least one material")

    parts = []
    for index, solid in enumerate(solids):
        product_name = part_names[index]
        part_uid = _unique_uid(_safe_uid(product_name), {part["part_uid"] for part in parts})
        parts.append(_extract_solid_part(solid, part_uid, product_name, index, path, material_ids[index % len(material_ids)]))

    inferred_connections = connections if connections is not None else infer_topology_connections(parts)
    return {
        "sample_id": sample,
        "schema_version": "0.1.0",
        "units": "mm",
        "parts": parts,
        "product_tree": {
            "assembly_id": sample,
            "root_part_uid": parts[0]["part_uid"],
            "parts": [
                {
                    "part_uid": part["part_uid"],
                    "name": part["name"],
                    "parent_uid": None if index == 0 else parts[0]["part_uid"],
                    "transform": transform_identity(),
                    "source_product_name": part["source_product_name"],
                    "source_solid_index": part["source_solid_index"],
                }
                for index, part in enumerate(parts)
            ],
        },
        "material_library": library,
        "connections": inferred_connections,
        "boundary_named_sets": {},
        "defects": [],
        "geometry_source": {
            "input_package_dir": str(path.parent.parent.resolve()) if path.parent.name == "geometry" else str(path.parent.resolve()),
            "step_file": str(path.resolve()),
            "step_descriptor_only": False,
            "cad_kernel": "STEP_AP242_BREP_OCP",
            "topology_extraction": "CadQuery/OCP solid-face-edge traversal",
            "step_validation": step_info,
        },
        "topology_traceability": {
            "source": "STEP_AP242_BREP_OCP",
            "step_file": str(path.resolve()),
            "product_names": product_names,
            "solid_count": len(solids),
            "part_count": len(parts),
            "face_count": sum(len(part["face_signatures"]) for part in parts),
            "edge_count": sum(len(part["topology_edges"]) for part in parts),
            "connection_inference": "nearest_bounding_box_chain" if connections is None else "metadata_connections",
        },
    }


def infer_topology_connections(parts: list[dict[str, Any]], max_connections: int | None = None) -> list[dict[str, Any]]:
    if len(parts) < 2:
        return []
    centers = {part["part_uid"]: _point(part["geometry_box"]["center"]) for part in parts}
    pairs = []
    for left_index, left in enumerate(parts):
        for right in parts[left_index + 1 :]:
            distance = _distance(centers[left["part_uid"]], centers[right["part_uid"]])
            pairs.append((distance, left["part_uid"], right["part_uid"]))
    pairs.sort()
    target_count = max_connections if max_connections is not None else max(1, min(len(parts) - 1, len(pairs)))
    selected = []
    used: set[str] = set()
    for _, left_uid, right_uid in pairs:
        if len(selected) >= target_count:
            break
        if left_uid in used and right_uid in used and len(selected) < len(parts) - 1:
            continue
        selected.append((left_uid, right_uid))
        used.add(left_uid)
        used.add(right_uid)
    if len(selected) < target_count:
        for _, left_uid, right_uid in pairs:
            if (left_uid, right_uid) not in selected:
                selected.append((left_uid, right_uid))
            if len(selected) >= target_count:
                break
    return [
        {
            "connection_uid": f"step_conn_{index:04d}",
            "type": "tied",
            "part_uid_a": left_uid,
            "part_uid_b": right_uid,
            "master_part_uid": left_uid,
            "slave_part_uid": right_uid,
            "feature_hint": "bbox_nearest_topology_contact",
            "diameter_mm": 3.0,
            "stiffness_profile": "STEP_default_tied",
            "washer_radius_mm": 5.0,
            "preserve_hole": False,
            "confidence": 0.75,
        }
        for index, (left_uid, right_uid) in enumerate(selected, start=1)
    ]


def _extract_solid_part(
    solid: Any,
    part_uid: str,
    product_name: str,
    source_solid_index: int,
    step_path: Path,
    material_id: str,
) -> dict[str, Any]:
    box = _bound_box(solid)
    faces = _extract_faces(solid, part_uid)
    edges = _extract_edges(solid, part_uid, faces)
    min_dim = max(0.05, min(box["dimensions"]))
    return {
        "part_uid": part_uid,
        "name": product_name,
        "source_product_name": product_name,
        "source_solid_index": source_solid_index,
        "source_step_file": str(step_path.resolve()),
        "material_id": material_id,
        "strategy": "solid",
        "nominal_thickness": round(float(min_dim), 6),
        "dimensions": {
            "length": round(float(box["dimensions"][0]), 6),
            "width": round(float(box["dimensions"][1]), 6),
            "height": round(float(box["dimensions"][2]), 6),
        },
        "geometry_box": {
            "origin": [round(value, 6) for value in box["origin"]],
            "dimensions": [round(value, 6) for value in box["dimensions"]],
            "center": [round(value, 6) for value in box["center"]],
        },
        "volume_mm3": round(_shape_volume(solid), 6),
        "surface_area_mm2": round(sum(float(face["area"]) for face in faces), 6),
        "features": [],
        "face_labels": [],
        "ports": [],
        "face_signatures": faces,
        "topology_edges": edges,
        "topology_source": "STEP_AP242_BREP_OCP",
    }


def _extract_faces(solid: Any, part_uid: str) -> list[dict[str, Any]]:
    faces = []
    for index, face in enumerate(solid.Faces()):
        face_uid = f"{part_uid}_face_{index:03d}"
        edges = list(face.Edges())
        perimeter = sum(_edge_length(edge) for edge in edges)
        center = _vector_tuple(face.Center())
        normal = _face_normal(face, center, _vector_tuple(solid.Center()))
        faces.append(
            {
                "face_uid": face_uid,
                "local_name": f"face_{index:03d}",
                "source_face_index": index,
                "source_face_hash": str(_shape_hash(face)),
                "area": round(float(face.Area()), 6),
                "perimeter": round(float(perimeter), 6),
                "centroid": [round(value, 6) for value in center],
                "normal": [round(value, 9) for value in normal],
            }
        )
    if not faces:
        raise StepTopologyError(f"solid {part_uid} contains no faces")
    return faces


def _extract_edges(solid: Any, part_uid: str, faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    faces_by_hash = {str(face["source_face_hash"]): face["face_uid"] for face in faces}
    face_edges: dict[str, list[str]] = {}
    edges_by_hash: dict[int, Any] = {}
    for face in solid.Faces():
        face_uid = faces_by_hash.get(str(_shape_hash(face)))
        if not face_uid:
            continue
        for edge in face.Edges():
            edge_hash = _shape_hash(edge)
            edges_by_hash[edge_hash] = edge
            face_edges.setdefault(str(edge_hash), []).append(face_uid)

    records = []
    for index, edge_hash in enumerate(sorted(edges_by_hash)):
        edge = edges_by_hash[edge_hash]
        incident = sorted(set(face_edges.get(str(edge_hash), [])))
        midpoint = _vector_tuple(edge.Center())
        tangent = _edge_tangent(edge)
        records.append(
            {
                "edge_uid": f"{part_uid}_edge_{index:03d}",
                "source_edge_index": index,
                "source_edge_hash": str(edge_hash),
                "length": round(_edge_length(edge), 6),
                "midpoint": [round(value, 6) for value in midpoint],
                "tangent": [round(value, 9) for value in tangent],
                "incident_face_uids": incident,
            }
        )
    if not records:
        raise StepTopologyError(f"solid {part_uid} contains no edges")
    return records


def _bound_box(shape: Any) -> dict[str, tuple[float, float, float]]:
    box = shape.BoundingBox()
    dims = (max(float(box.xlen), 1.0e-6), max(float(box.ylen), 1.0e-6), max(float(box.zlen), 1.0e-6))
    origin = (float(box.xmin), float(box.ymin), float(box.zmin))
    center = _vector_tuple(box.center)
    return {"origin": origin, "dimensions": dims, "center": center}


def _shape_volume(shape: Any) -> float:
    try:
        return float(shape.Volume())
    except Exception:
        box = _bound_box(shape)
        dims = box["dimensions"]
        return float(dims[0] * dims[1] * dims[2])


def _edge_length(edge: Any) -> float:
    try:
        return float(edge.Length())
    except Exception:
        return 0.0


def _edge_tangent(edge: Any) -> tuple[float, float, float]:
    for args in ((), (0.5,)):
        try:
            return _unit(_vector_tuple(edge.tangentAt(*args)))
        except Exception:
            continue
    return (1.0, 0.0, 0.0)


def _face_normal(face: Any, center: tuple[float, float, float], solid_center: tuple[float, float, float]) -> tuple[float, float, float]:
    try:
        return _unit(_vector_tuple(face.normalAt()))
    except Exception:
        return _unit((center[0] - solid_center[0], center[1] - solid_center[1], center[2] - solid_center[2]))


def _shape_hash(shape: Any) -> int:
    try:
        return int(shape.hashCode())
    except Exception:
        return id(shape)


def _vector_tuple(value: Any) -> tuple[float, float, float]:
    if hasattr(value, "toTuple"):
        seq = value.toTuple()
    else:
        seq = value
    return (float(seq[0]), float(seq[1]), float(seq[2]))


def _point(values: Any) -> tuple[float, float, float]:
    seq = list(values)
    return (float(seq[0]), float(seq[1]), float(seq[2]))


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2) ** 0.5


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = _distance((0.0, 0.0, 0.0), vector)
    if norm <= 1.0e-12:
        return (1.0, 0.0, 0.0)
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _step_product_names(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    names = [item.replace("''", "'") for item in re.findall(r"PRODUCT\(\s*'((?:[^']|'')*)'", text)]
    result = []
    for name in names:
        clean = name.strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _part_names_for_solids(product_names: list[str], solid_count: int, sample_id: str) -> list[str]:
    if len(product_names) >= solid_count + 1:
        candidates = product_names[-solid_count:]
    elif len(product_names) >= solid_count:
        candidates = product_names[:solid_count]
    else:
        candidates = product_names + [f"{sample_id}_part_{index:03d}" for index in range(len(product_names), solid_count)]
    return candidates


def _safe_uid(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not cleaned:
        cleaned = "step_entity"
    if cleaned[0].isdigit():
        cleaned = f"p_{cleaned}"
    return cleaned[:96]


def _unique_uid(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    index = 2
    while f"{base}_{index}" in used:
        index += 1
    return f"{base}_{index}"
