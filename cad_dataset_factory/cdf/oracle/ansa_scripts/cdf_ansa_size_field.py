"""ANSA-internal size-field evaluator for CDF v2 entity samples.

This module is intentionally importable in normal Python.  Real ANSA imports are
lazy and stay inside ``ansa_scripts`` so normal unit tests can exercise the
workflow with a fake adapter.
"""

from __future__ import annotations

import base64
import json
import math
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class SizeFieldScriptError(RuntimeError):
    """Structured failure inside the ANSA size-field script."""

    def __init__(self, code: str, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        self.code = code
        self.diagnostics = diagnostics or {}
        super().__init__(f"{code}: {message}")


class SizeFieldAnsaAdapter(Protocol):
    """Small adapter surface needed by the size-field workflow."""

    def ansa_version(self) -> str: ...

    def import_step(self, cad_path: str) -> bool: ...

    def cleanup_geometry(self) -> bool: ...

    def extract_midsurface(self) -> bool: ...

    def collect_edge_descriptors(self) -> list[dict[str, Any]]: ...

    def collect_face_descriptors(self) -> list[dict[str, Any]]: ...

    def apply_global_mesh(self, h0_mm: float, h_min_mm: float, h_max_mm: float, growth_rate: float) -> None: ...

    def apply_edge_size(self, entity: Any, target_size_mm: float) -> None: ...

    def apply_face_size(self, entity: Any, target_size_mm: float) -> None: ...

    def run_batch_mesh(self, session_name: str, timeout_sec: int) -> bool: ...

    def export_solver_deck(self, mesh_path: str, solver_deck: str) -> bool: ...

    def global_quality(self) -> dict[str, Any]: ...

    def measure_entity_length_stats(self, entity: Any) -> dict[str, float] | None: ...


@dataclass(frozen=True)
class EntityDescriptor:
    signature_id: str | None
    index: int
    entity_type: str
    entity: Any | None
    length: float | None = None
    area: float | None = None
    curve_type_id: int | None = None
    bbox: tuple[float, float, float] | None = None
    center: tuple[float, float, float] | None = None
    anchor: tuple[float, float, float] | None = None
    endpoint: tuple[float, float, float] | None = None
    raw: dict[str, Any] | None = None


def decode_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    if not isinstance(decoded, dict):
        raise SizeFieldScriptError("payload_not_object", "ANSA process payload must be a JSON object")
    return decoded


def payload_from_program_arguments() -> dict[str, Any]:
    try:
        from ansa import session  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - only real ANSA path.
        raise SizeFieldScriptError("ansa_api_unavailable", "ANSA Python modules are not available") from exc
    for item in session.ProgramArguments():
        if isinstance(item, str) and item.startswith("-process_string:"):
            return decode_payload(item[len("-process_string:") :])
    raise SizeFieldScriptError("missing_process_string", "ANSA command did not provide -process_string")


def _read_json(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SizeFieldScriptError("json_not_object", f"expected JSON object: {path}")
    return raw


def _write_json(path: str | Path, document: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tuple3(values: Any) -> tuple[float, float, float] | None:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        return None
    try:
        return (float(values[0]), float(values[1]), float(values[2]))
    except (TypeError, ValueError):
        return None


def _parse_point(value: Any) -> tuple[float, float, float] | None:
    if value is not None and not isinstance(value, (str, list, tuple)):
        value = str(value)
    if isinstance(value, str):
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", value)
        if len(numbers) >= 3:
            try:
                return (float(numbers[0]), float(numbers[1]), float(numbers[2]))
            except ValueError:
                return None
    return _tuple3(value)


def cdf_edge_descriptors(graph_npz: str | Path, entity_signatures: dict[str, Any]) -> list[EntityDescriptor]:
    import numpy as np

    with np.load(graph_npz, allow_pickle=False) as arrays:
        rows = arrays["edge_features"]
    descriptors: list[EntityDescriptor] = []
    for record in entity_signatures.get("edges", []):
        index = int(record["index"])
        row = rows[index]
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        vertex_points = fingerprint.get("vertex_points_mm") if isinstance(fingerprint.get("vertex_points_mm"), list) else []
        anchor = _tuple3(vertex_points[0]) if len(vertex_points) >= 1 else None
        endpoint = _tuple3(vertex_points[1]) if len(vertex_points) >= 2 else None
        descriptors.append(
            EntityDescriptor(
                signature_id=str(record["signature_id"]),
                index=index,
                entity_type="EDGE",
                entity=None,
                curve_type_id=int(fingerprint.get("curve_type_id", round(float(row[0])))),
                length=_positive_float(fingerprint.get("length_mm")) or float(row[1]),
                bbox=_tuple3(fingerprint.get("bbox_mm")) or (float(row[2]), float(row[3]), float(row[4])),
                center=_tuple3(fingerprint.get("center_mm")) or (float(row[5]), float(row[6]), float(row[7])),
                anchor=anchor,
                endpoint=endpoint,
            )
        )
    return descriptors


def cdf_face_descriptors(graph_npz: str | Path, entity_signatures: dict[str, Any]) -> list[EntityDescriptor]:
    import numpy as np

    with np.load(graph_npz, allow_pickle=False) as arrays:
        rows = arrays["face_features"]
    descriptors: list[EntityDescriptor] = []
    for record in entity_signatures.get("faces", []):
        index = int(record["index"])
        row = rows[index]
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        descriptors.append(
            EntityDescriptor(
                signature_id=str(record["signature_id"]),
                index=index,
                entity_type="FACE",
                entity=None,
                area=_positive_float(fingerprint.get("area_mm2")) or float(row[0]),
                bbox=_tuple3(fingerprint.get("bbox_mm")) or (float(row[1]), float(row[2]), float(row[3])),
                center=_tuple3(fingerprint.get("center_mm")) or (float(row[4]), float(row[5]), float(row[6])),
            )
        )
    return descriptors


def _adapter_descriptor(raw: dict[str, Any], entity_type: str, index: int) -> EntityDescriptor:
    raw_cards = raw.get("raw_card_values") if isinstance(raw.get("raw_card_values"), dict) else {}
    anchor = _tuple3(raw.get("anchor")) or _parse_point(raw_cards.get("Start Point"))
    endpoint = _parse_point(raw_cards.get("End Point"))
    center = _tuple3(raw.get("center"))
    bbox = _tuple3(raw.get("bbox"))
    if center is None and anchor is not None and endpoint is not None:
        center = tuple((left + right) * 0.5 for left, right in zip(anchor, endpoint, strict=True))  # type: ignore[assignment]
    if bbox is None and anchor is not None and endpoint is not None:
        bbox = tuple(abs(left - right) for left, right in zip(anchor, endpoint, strict=True))  # type: ignore[assignment]
    return EntityDescriptor(
        signature_id=raw.get("signature_id") if isinstance(raw.get("signature_id"), str) else None,
        index=int(raw.get("index", index)),
        entity_type=entity_type,
        entity=raw.get("entity"),
        length=_positive_float(raw.get("length")),
        area=_positive_float(raw.get("area")),
        curve_type_id=int(raw["curve_type_id"]) if raw.get("curve_type_id") is not None else None,
        bbox=bbox,
        center=center,
        anchor=anchor,
        endpoint=endpoint,
        raw=raw_cards or None,
    )


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _positive_float(value: Any) -> float | None:
    numeric = _optional_float(value)
    if numeric is None or numeric <= 0:
        return None
    return numeric


def _distance(left: tuple[float, float, float] | None, right: tuple[float, float, float] | None) -> float | None:
    if left is None or right is None:
        return None
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _endpoint_pair_distance(left: EntityDescriptor, right: EntityDescriptor) -> float | None:
    if left.anchor is None or left.endpoint is None or right.anchor is None or right.endpoint is None:
        return None
    same = _distance(left.anchor, right.anchor) + _distance(left.endpoint, right.endpoint)  # type: ignore[operator]
    flipped = _distance(left.anchor, right.endpoint) + _distance(left.endpoint, right.anchor)  # type: ignore[operator]
    return min(same, flipped) * 0.5


def _relative_error(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) / scale


def _matching_radius(descriptor: EntityDescriptor) -> float | None:
    if descriptor.curve_type_id != 2:
        return None
    if descriptor.bbox is not None:
        radius = max(abs(value) for value in descriptor.bbox) * 0.5
        if radius > 1.0e-9:
            return radius
    if descriptor.length is not None:
        if descriptor.anchor is not None and descriptor.endpoint is not None:
            chord = _distance(descriptor.anchor, descriptor.endpoint)
            if chord is not None and chord > 1.0e-9 and abs(descriptor.length - math.pi * chord * 0.5) / max(descriptor.length, 1.0) < 0.1:
                return chord * 0.5
        if descriptor.length > 0:
            return descriptor.length / (2.0 * math.pi)
    return None


def _matching_plane_axis(descriptor: EntityDescriptor) -> int | None:
    if descriptor.bbox is None:
        return None
    if abs(descriptor.bbox[2]) <= 1.0e-9:
        return 2
    return min(range(3), key=lambda index: abs(descriptor.bbox[index]))


def _candidate_mismatch_details(cdf: EntityDescriptor, ansa: EntityDescriptor, tolerance_mm: float, relative_tolerance: float) -> dict[str, Any]:
    length_error = _relative_error(cdf.length, ansa.length)
    area_error = _relative_error(cdf.area, ansa.area)
    endpoint_distance = _endpoint_pair_distance(cdf, ansa)
    center_distance = _distance(cdf.center, ansa.center)
    bbox_distance = _distance(cdf.bbox, ansa.bbox)
    anchor_distance = _distance(cdf.anchor, ansa.anchor)
    radius_error = _relative_error(_matching_radius(cdf), _matching_radius(ansa))
    plane_match = _matching_plane_axis(cdf) == _matching_plane_axis(ansa) if _matching_plane_axis(cdf) is not None and _matching_plane_axis(ansa) is not None else None
    return {
        "ansa_index": ansa.index,
        "length_error": length_error,
        "area_error": area_error,
        "endpoint_distance_mm": endpoint_distance,
        "center_distance_mm": center_distance,
        "bbox_distance_mm": bbox_distance,
        "anchor_distance_mm": anchor_distance,
        "radius_error": radius_error,
        "plane_match": plane_match,
        "passes_length": length_error is None or length_error <= relative_tolerance,
        "passes_area": area_error is None or area_error <= relative_tolerance,
        "passes_endpoint": endpoint_distance is None or endpoint_distance <= tolerance_mm,
        "passes_radius": radius_error is None or radius_error <= relative_tolerance,
        "passes_plane": plane_match is None or plane_match,
    }


def _descriptor_score(
    cdf: EntityDescriptor,
    ansa: EntityDescriptor,
    *,
    tolerance_mm: float,
    relative_tolerance: float,
) -> float | None:
    if cdf.curve_type_id is not None and ansa.curve_type_id is not None and cdf.curve_type_id != ansa.curve_type_id:
        return None
    length_error = _relative_error(cdf.length, ansa.length)
    area_error = _relative_error(cdf.area, ansa.area)
    radius_error = _relative_error(_matching_radius(cdf), _matching_radius(ansa))
    endpoint_distance = _endpoint_pair_distance(cdf, ansa)
    center_distance = _distance(cdf.center, ansa.center)
    bbox_distance = _distance(cdf.bbox, ansa.bbox)
    anchor_distance = _distance(cdf.anchor, ansa.anchor)
    if all(value is None for value in (length_error, area_error, radius_error, endpoint_distance, center_distance, bbox_distance, anchor_distance)):
        return None
    if length_error is not None and length_error > relative_tolerance:
        return None
    if area_error is not None and area_error > relative_tolerance:
        return None
    if radius_error is not None and radius_error > relative_tolerance:
        return None
    if cdf.entity_type == "EDGE" and cdf.curve_type_id in {1, 2}:
        spatial = endpoint_distance
        if spatial is None and cdf.curve_type_id == 2:
            spatial = anchor_distance
        if spatial is None:
            spatial = center_distance
    else:
        spatial = center_distance
    if spatial is None:
        spatial = bbox_distance
    if spatial is not None and spatial > tolerance_mm:
        return None
    if cdf.entity_type == "EDGE" and cdf.curve_type_id == 2:
        cdf_plane = _matching_plane_axis(cdf)
        ansa_plane = _matching_plane_axis(ansa)
        if cdf_plane is not None and ansa_plane is not None and cdf_plane != ansa_plane:
            return None
    score = sum(value for value in (length_error, area_error, radius_error) if value is not None)
    if spatial is not None:
        score += spatial / max(tolerance_mm, 1.0e-9)
    return score


def match_descriptors(
    cdf_descriptors: list[EntityDescriptor],
    ansa_descriptors: list[EntityDescriptor],
    *,
    tolerance_mm: float = 0.2,
    relative_tolerance: float = 0.02,
) -> dict[str, EntityDescriptor]:
    matches: dict[str, EntityDescriptor] = {}
    used: set[int] = set()
    diagnostics: dict[str, Any] = {"unmatched": [], "ambiguous": []}
    for cdf in cdf_descriptors:
        if not cdf.signature_id:
            continue
        candidates: list[tuple[float, EntityDescriptor]] = []
        nearest: list[dict[str, Any]] = []
        for ansa in ansa_descriptors:
            if ansa.index in used:
                continue
            details = _candidate_mismatch_details(cdf, ansa, tolerance_mm, relative_tolerance)
            rough_score = sum(
                float(value)
                for value in (
                    details["length_error"],
                    details["area_error"],
                    details["radius_error"],
                    (details["endpoint_distance_mm"] / max(tolerance_mm, 1.0e-9)) if details["endpoint_distance_mm"] is not None else None,
                    (details["center_distance_mm"] / max(tolerance_mm, 1.0e-9)) if details["center_distance_mm"] is not None else None,
                )
                if value is not None
            )
            details["rough_score"] = rough_score
            nearest.append(details)
            score = _descriptor_score(cdf, ansa, tolerance_mm=tolerance_mm, relative_tolerance=relative_tolerance)
            if score is not None:
                candidates.append((score, ansa))
        candidates.sort(key=lambda item: (item[0], item[1].index))
        nearest.sort(key=lambda item: float(item["rough_score"]))
        if candidates and (len(candidates) == 1 or candidates[1][0] - candidates[0][0] > 1.0e-6):
            match = candidates[0][1]
            matches[cdf.signature_id] = match
            used.add(match.index)
        elif not candidates:
            diagnostics["unmatched"].append({"signature_id": cdf.signature_id, "nearest_candidates": nearest[:5]})
        else:
            diagnostics["ambiguous"].append(
                {
                    "signature_id": cdf.signature_id,
                    "candidate_count": len(candidates),
                    "candidate_indices": [item[1].index for item in candidates[:5]],
                    "candidate_scores": [item[0] for item in candidates[:5]],
                }
            )
    if diagnostics["unmatched"] or diagnostics["ambiguous"]:
        raise SizeFieldScriptError("entity_matching_failed", "CDF entity descriptors could not be matched to ANSA entities", diagnostics)
    return matches


def measure_bdf_entity_length_stats(mesh_path: str | Path, descriptor: EntityDescriptor, target_size_mm: float) -> dict[str, float] | None:
    """Measure mesh segment lengths that lie on a CDF edge descriptor.

    This is deliberately based on the exported solver deck, not on target values
    or ANSA success messages.  If the exported mesh cannot be associated with
    the CAD edge geometry, the metric is unavailable and the workflow remains
    fail-closed.
    """

    if descriptor.entity_type != "EDGE":
        return None
    points, element_edges = _read_bdf_shell_edges(mesh_path)
    if not points or not element_edges:
        return None
    tolerance = max(0.05, min(1.5, target_size_mm * 0.45))
    lengths: list[float] = []
    for start_id, end_id in element_edges:
        start = points.get(start_id)
        end = points.get(end_id)
        if start is None or end is None:
            continue
        if _mesh_edge_matches_descriptor(start, end, descriptor, tolerance):
            length = _point_distance(start, end)
            if length > 1.0e-9:
                lengths.append(length)
    if not lengths:
        return None
    return {
        "average": sum(lengths) / len(lengths),
        "min": min(lengths),
        "max": max(lengths),
        "count": float(len(lengths)),
    }


def _read_bdf_shell_edges(mesh_path: str | Path) -> tuple[dict[int, tuple[float, float, float]], set[tuple[int, int]]]:
    points: dict[int, tuple[float, float, float]] = {}
    edges: set[tuple[int, int]] = set()
    for raw_line in Path(mesh_path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("$"):
            continue
        card = line[:8].strip().upper()
        fields = _nastran_fields(line)
        if card == "GRID":
            node_id = _int_field(fields, 1)
            xyz = (_float_field(fields, 3), _float_field(fields, 4), _float_field(fields, 5))
            if node_id is not None and all(value is not None for value in xyz):
                points[node_id] = (float(xyz[0]), float(xyz[1]), float(xyz[2]))  # type: ignore[arg-type]
        elif card in {"CTRIA3", "CQUAD4"}:
            node_ids = [_int_field(fields, index) for index in (3, 4, 5, 6)]
            clean_ids = [int(node_id) for node_id in node_ids if node_id is not None and node_id > 0]
            if card == "CTRIA3":
                clean_ids = clean_ids[:3]
            elif card == "CQUAD4":
                clean_ids = clean_ids[:4]
            if len(clean_ids) >= 3:
                for left, right in zip(clean_ids, clean_ids[1:] + clean_ids[:1]):
                    edges.add(tuple(sorted((left, right))))
    return points, edges


def _nastran_fields(line: str) -> list[str]:
    if "," in line:
        return [field.strip() for field in line.split(",")]
    return [line[index : index + 8].strip() for index in range(0, len(line), 8)]


def _int_field(fields: list[str], index: int) -> int | None:
    if index >= len(fields) or not fields[index]:
        return None
    try:
        return int(float(fields[index].replace("D", "E")))
    except ValueError:
        return None


def _float_field(fields: list[str], index: int) -> float | None:
    if index >= len(fields) or not fields[index]:
        return None
    value = fields[index].replace("D", "E")
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _mesh_edge_matches_descriptor(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    descriptor: EntityDescriptor,
    tolerance: float,
) -> bool:
    if descriptor.curve_type_id == 2:
        return _mesh_edge_matches_circle(start, end, descriptor, tolerance)
    return _mesh_edge_matches_line(start, end, descriptor, tolerance)


def _mesh_edge_matches_line(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    descriptor: EntityDescriptor,
    tolerance: float,
) -> bool:
    endpoints = _descriptor_line_endpoints(descriptor)
    if endpoints is None:
        return False
    line_start, line_end = endpoints
    if _point_segment_distance(start, line_start, line_end) > tolerance:
        return False
    if _point_segment_distance(end, line_start, line_end) > tolerance:
        return False
    return True


def _mesh_edge_matches_circle(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    descriptor: EntityDescriptor,
    tolerance: float,
) -> bool:
    center = _circle_center(descriptor)
    radius = _descriptor_radius(descriptor)
    if center is None or radius is None:
        return False
    plane_axis = _circle_plane_axis(descriptor)
    for point in (start, end):
        if abs(point[plane_axis] - center[plane_axis]) > tolerance:
            return False
        radial = math.sqrt(sum((point[index] - center[index]) ** 2 for index in range(3) if index != plane_axis))
        if abs(radial - radius) > tolerance:
            return False
    return True


def _circle_center(descriptor: EntityDescriptor) -> tuple[float, float, float] | None:
    if descriptor.anchor is not None and descriptor.endpoint is not None:
        return tuple((left + right) * 0.5 for left, right in zip(descriptor.anchor, descriptor.endpoint, strict=True))  # type: ignore[return-value]
    return descriptor.center


def _descriptor_line_endpoints(descriptor: EntityDescriptor) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if descriptor.anchor is not None and descriptor.endpoint is not None:
        return descriptor.anchor, descriptor.endpoint
    if descriptor.anchor is None or descriptor.center is None:
        return None
    other = tuple(2.0 * center - anchor for center, anchor in zip(descriptor.center, descriptor.anchor, strict=True))
    return descriptor.anchor, other  # type: ignore[return-value]


def _descriptor_radius(descriptor: EntityDescriptor) -> float | None:
    radius = _matching_radius(descriptor)
    if radius is not None:
        return radius
    if descriptor.bbox is not None:
        radius = max(descriptor.bbox) * 0.5
        if radius > 0:
            return radius
    if descriptor.length is not None and descriptor.length > 0:
        return descriptor.length / (2.0 * math.pi)
    return None


def _circle_plane_axis(descriptor: EntityDescriptor) -> int:
    return _matching_plane_axis(descriptor) or 2


def _point_distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _point_segment_distance(
    point: tuple[float, float, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> float:
    segment = tuple(right - left for left, right in zip(start, end, strict=True))
    length_sq = sum(value * value for value in segment)
    if length_sq <= 1.0e-12:
        return _point_distance(point, start)
    offset = tuple(value - left for value, left in zip(point, start, strict=True))
    t = max(0.0, min(1.0, sum(a * b for a, b in zip(offset, segment, strict=True)) / length_sq))
    projection = tuple(left + t * delta for left, delta in zip(start, segment, strict=True))
    return _point_distance(point, projection)  # type: ignore[arg-type]


def build_entity_quality_rows(
    *,
    edge_sizes: list[dict[str, Any]],
    face_sizes: list[dict[str, Any]],
    edge_matches: dict[str, EntityDescriptor],
    face_matches: dict[str, EntityDescriptor],
    cdf_edges: dict[str, EntityDescriptor],
    mesh_path: str | Path,
    adapter: SizeFieldAnsaAdapter,
    growth_rate: float,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    all_available = True
    for record in edge_sizes:
        signature_id = record["edge_signature_id"]
        target = float(record["target_size_mm"])
        match = edge_matches[signature_id]
        stats = adapter.measure_entity_length_stats(match.entity)
        if stats is None:
            stats = measure_bdf_entity_length_stats(mesh_path, cdf_edges[signature_id], target)
        row = _quality_row(signature_id, "EDGE", target, growth_rate, stats)
        rows.append(row)
        all_available = all_available and row["metric_available"]
    for record in face_sizes:
        signature_id = record["face_signature_id"]
        target = float(record["target_size_mm"])
        match = face_matches[signature_id]
        stats = adapter.measure_entity_length_stats(match.entity)
        row = _quality_row(signature_id, "FACE", target, growth_rate, stats)
        rows.append(row)
        all_available = all_available and row["metric_available"]
    return rows, all_available


def _quality_row(signature_id: str, entity_type: str, target: float, growth_rate: float, stats: dict[str, float] | None) -> dict[str, Any]:
    if not stats or _optional_float(stats.get("average")) is None:
        return {
            "entity_signature_id": signature_id,
            "entity_type": entity_type,
            "candidate_target_size_mm": target,
            "candidate_growth_rate": growth_rate,
            "measured_quality_margin": 1.0,
            "hard_fail": True,
            "near_fail": True,
            "metric_available": False,
            "metric_unavailable_reason": "entity_length_statistics_unavailable",
        }
    measured = float(stats["average"])
    boundary_error = abs(measured - target) / target
    return {
        "entity_signature_id": signature_id,
        "entity_type": entity_type,
        "candidate_target_size_mm": target,
        "candidate_neighbor_size_ratio_max": growth_rate,
        "candidate_growth_rate": growth_rate,
        "measured_edge_length_mean_mm": measured,
        "measured_edge_length_min_mm": float(stats.get("min", measured)),
        "measured_edge_length_max_mm": float(stats.get("max", measured)),
        "measured_edge_segment_count": int(stats.get("count", 1)),
        "measured_quality_margin": boundary_error - 0.5,
        "measured_boundary_size_error": boundary_error,
        "hard_fail": boundary_error > 0.5,
        "near_fail": boundary_error > 0.35,
        "metric_available": True,
    }


def run_size_field_workflow(payload: dict[str, Any], adapter: SizeFieldAnsaAdapter) -> int:
    started = time.monotonic()
    sample_id = str(payload["sample_id"])
    evaluation_id = str(payload.get("evaluation_id") or "evaluation_000001")
    execution: dict[str, Any] = _execution_report(sample_id, adapter.ansa_version())
    quality: dict[str, Any] = _quality_report(sample_id)
    diagnostics: dict[str, Any] = {"sample_id": sample_id, "status": "STARTED"}
    try:
        size_field = _read_json(payload["size_field"])
        signatures = _read_json(payload["entity_signatures"])
        edge_records = list(size_field.get("edge_sizes", []))
        face_records = list(size_field.get("face_sizes", []))
        global_mesh = dict(size_field["global_mesh"])

        execution["step_import_success"] = bool(adapter.import_step(str(payload["cad_path"])))
        if not execution["step_import_success"]:
            raise SizeFieldScriptError("step_import_failed", "ANSA could not import the STEP file")
        execution["geometry_cleanup_success"] = bool(adapter.cleanup_geometry())
        execution["midsurface_extraction_success"] = bool(adapter.extract_midsurface())
        if not execution["midsurface_extraction_success"]:
            raise SizeFieldScriptError("midsurface_extraction_failed", "ANSA could not create shell/midsurface entities")

        cdf_edges = cdf_edge_descriptors(payload["graph_npz"], signatures)
        cdf_faces = cdf_face_descriptors(payload["graph_npz"], signatures)
        ansa_edges = [_adapter_descriptor(item, "EDGE", index) for index, item in enumerate(adapter.collect_edge_descriptors())]
        ansa_faces = [_adapter_descriptor(item, "FACE", index) for index, item in enumerate(adapter.collect_face_descriptors())]
        diagnostics["descriptor_counts"] = {
            "cdf_edges": len(cdf_edges),
            "cdf_faces": len(cdf_faces),
            "ansa_edges": len(ansa_edges),
            "ansa_faces": len(ansa_faces),
            "requested_edge_sizes": len(edge_records),
            "requested_face_sizes": len(face_records),
        }
        diagnostics["ansa_edge_descriptors"] = [_descriptor_diagnostic(item) for item in ansa_edges[:50]]
        diagnostics["cdf_edge_descriptors"] = [_descriptor_diagnostic(item) for item in cdf_edges[:50]]
        requested_edge_ids = {record["edge_signature_id"] for record in edge_records}
        requested_face_ids = {record["face_signature_id"] for record in face_records}
        edge_matches = match_descriptors([item for item in cdf_edges if item.signature_id in requested_edge_ids], ansa_edges)
        face_matches = match_descriptors([item for item in cdf_faces if item.signature_id in requested_face_ids], ansa_faces) if face_records else {}
        execution["feature_matching_success"] = True

        adapter.apply_global_mesh(float(global_mesh["h0_mm"]), float(global_mesh["h_min_mm"]), float(global_mesh["h_max_mm"]), float(global_mesh["growth_rate"]))
        for record in edge_records:
            adapter.apply_edge_size(edge_matches[record["edge_signature_id"]].entity, float(record["target_size_mm"]))
        for record in face_records:
            adapter.apply_face_size(face_matches[record["face_signature_id"]].entity, float(record["target_size_mm"]))
        execution["batch_mesh_success"] = bool(adapter.run_batch_mesh(str(payload["batch_mesh_session"]), int(payload.get("timeout_sec", 240))))
        if not execution["batch_mesh_success"]:
            raise SizeFieldScriptError("batch_mesh_failed", "ANSA batch/surface mesh did not complete")
        execution["solver_export_success"] = bool(adapter.export_solver_deck(str(payload["mesh_path"]), str(payload["solver_deck"])))
        mesh_path = Path(payload["mesh_path"])
        if not execution["solver_export_success"] or not mesh_path.is_file() or mesh_path.stat().st_size <= 0:
            raise SizeFieldScriptError("solver_export_failed", "ANSA did not write a non-empty BDF mesh")

        global_quality = adapter.global_quality()
        num_hard_failed = int(global_quality.get("num_hard_failed_elements", 0))
        rows, local_metrics_available = build_entity_quality_rows(
            edge_sizes=edge_records,
            face_sizes=face_records,
            edge_matches=edge_matches,
            face_matches=face_matches,
            cdf_edges={item.signature_id: item for item in cdf_edges if item.signature_id},
            mesh_path=payload["mesh_path"],
            adapter=adapter,
            growth_rate=float(global_mesh["growth_rate"]),
        )
        local_hard_fail = any(row["hard_fail"] for row in rows)
        accepted = num_hard_failed == 0 and local_metrics_available and not local_hard_fail
        execution["accepted"] = accepted
        execution["outputs"] = {
            "mesh": str(payload["mesh_path"]),
            "entity_quality": str(payload["entity_quality"]),
            "diagnostics": str(payload["diagnostics"]),
        }
        quality.update(
            {
                "accepted": accepted,
                "mesh_stats": dict(global_quality.get("mesh_stats", {})),
                "quality": {
                    "num_hard_failed_elements": num_hard_failed,
                    "entity_local_metrics_available": local_metrics_available,
                },
                "feature_checks": [
                    {
                        "feature_id": row["entity_signature_id"],
                        "type": row["entity_type"],
                        "target_edge_length_mm": row["candidate_target_size_mm"],
                        "measured_boundary_length_mm": row.get("measured_edge_length_mean_mm"),
                        "boundary_size_error": row.get("measured_boundary_size_error"),
                    }
                    for row in rows
                    if row.get("metric_available")
                ],
            }
        )
        entity_quality = {
            "schema_version": "CDF_ENTITY_QUALITY_EVALUATION_SM_V2",
            "sample_id": sample_id,
            "evaluation_id": evaluation_id,
            "size_field_path": _sample_relative_path(payload["sample_dir"], payload["size_field"]),
            "entity_quality": rows,
            "global_quality_summary": {
                "num_hard_failed_elements": num_hard_failed,
                "mesh_stats": dict(global_quality.get("mesh_stats", {})),
                "accepted": accepted,
            },
        }
        diagnostics.update({"status": "SUCCESS" if accepted else "FAILED", "edge_match_count": len(edge_matches), "face_match_count": len(face_matches)})
        _write_json(payload["entity_quality"], entity_quality)
        return_code = 0 if accepted else 2
    except Exception as exc:  # noqa: BLE001 - script must write controlled reports on every failure.
        if isinstance(exc, SizeFieldScriptError):
            code = exc.code
            diag = exc.diagnostics
        else:
            code = type(exc).__name__
            diag = {}
        execution["outputs"] = {"diagnostics": str(payload["diagnostics"])}
        quality["quality"] = {"num_hard_failed_elements": 0, "entity_local_metrics_available": False}
        diagnostics.update({"status": "BLOCKED", "error_code": code, "message": str(exc), "details": diag, "traceback": traceback.format_exc()})
        _write_json(
            payload["entity_quality"],
            {
                "schema_version": "CDF_ENTITY_QUALITY_EVALUATION_SM_V2",
                "sample_id": sample_id,
                "evaluation_id": evaluation_id,
                "size_field_path": _sample_relative_path(payload["sample_dir"], payload["size_field"]),
                "entity_quality": [
                    {
                        "entity_signature_id": "UNMATCHED",
                        "entity_type": "EDGE",
                        "candidate_target_size_mm": 1.0,
                        "candidate_growth_rate": 1.0,
                        "measured_quality_margin": 1.0,
                        "hard_fail": True,
                        "near_fail": True,
                        "metric_available": False,
                        "metric_unavailable_reason": code,
                    }
                ],
                "global_quality_summary": {"accepted": False, "blocked_reason": code},
            },
        )
        return_code = 2
    finally:
        execution["runtime_sec"] = max(0.0, time.monotonic() - started)
        _write_json(payload["execution_report"], execution)
        _write_json(payload["quality_report"], quality)
        _write_json(payload["diagnostics"], diagnostics)
    return return_code


def _sample_relative_path(sample_dir: str | Path, path: str | Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(sample_dir).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _descriptor_diagnostic(descriptor: EntityDescriptor) -> dict[str, Any]:
    return {
        "signature_id": descriptor.signature_id,
        "index": descriptor.index,
        "entity_type": descriptor.entity_type,
        "length": descriptor.length,
        "area": descriptor.area,
        "curve_type_id": descriptor.curve_type_id,
        "bbox": descriptor.bbox,
        "center": descriptor.center,
        "anchor": descriptor.anchor,
        "endpoint": descriptor.endpoint,
        "radius": _matching_radius(descriptor),
        "plane_axis": _matching_plane_axis(descriptor),
        "raw": descriptor.raw,
        "has_entity": descriptor.entity is not None,
    }


def _execution_report(sample_id: str, ansa_version: str) -> dict[str, Any]:
    return {
        "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
        "sample_id": sample_id,
        "accepted": False,
        "ansa_version": ansa_version,
        "step_import_success": False,
        "geometry_cleanup_success": False,
        "midsurface_extraction_success": False,
        "feature_matching_success": False,
        "batch_mesh_success": False,
        "solver_export_success": False,
        "runtime_sec": 0.0,
        "outputs": {},
    }


def _quality_report(sample_id: str) -> dict[str, Any]:
    return {
        "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
        "sample_id": sample_id,
        "accepted": False,
        "mesh_stats": {},
        "quality": {"num_hard_failed_elements": 0, "entity_local_metrics_available": False},
        "feature_checks": [],
    }


class RealAnsaSizeFieldAdapter:
    """Best-effort ANSA v25.1 adapter with fail-closed metric behavior."""

    def __init__(self) -> None:
        from ansa import base, batchmesh, constants, mesh  # type: ignore[import-not-found]

        self.base = base
        self.batchmesh = batchmesh
        self.constants = constants
        self.mesh = mesh
        self.deck = constants.NASTRAN

    def ansa_version(self) -> str:
        return str(getattr(self.constants, "version", getattr(self.constants, "VERSION", "unknown")))

    def import_step(self, cad_path: str) -> bool:
        return int(self.base.Open(cad_path)) == 0

    def cleanup_geometry(self) -> bool:
        try:
            faces = self.base.CollectEntities(self.deck, None, "FACE")
            if not faces:
                return True
            result = self.base.CheckAndFixGeometry(faces, ["UNCHECKED FACES", "SINGLE CONS"], [1, 1], True, True)
            return result is None or isinstance(result, dict)
        except Exception:
            return False

    def extract_midsurface(self) -> bool:
        try:
            faces = self.base.CollectEntities(self.deck, None, "FACE")
            if faces:
                result = self.base.Skin(entities=faces, apply_thickness=True, new_pid=True, offset_type=3, ok_to_offset=True, delete=False)
                return result is not None
            return True
        except TypeError:
            try:
                return self.base.Skin(True, True, 3, True, 20.0, False, [], 70, False, True) is not None
            except Exception:
                return False
        except Exception:
            return False

    def collect_edge_descriptors(self) -> list[dict[str, Any]]:
        entities = []
        for entity_type in ("CONS", "FE PERIMETER", "CURVE"):
            try:
                entities.extend(self.base.CollectEntities(self.deck, None, entity_type))
            except Exception:
                continue
        descriptors: list[dict[str, Any]] = []
        for index, entity in enumerate(entities):
            raw_card_values = self._all_card_values(entity)
            endpoints = self._endpoints_from_values(raw_card_values) or self._endpoints(entity)
            descriptors.append(
                {
                    "index": index,
                    "entity": entity,
                    "length": self._length(entity) or _positive_float(raw_card_values.get("Length")),
                    "curve_type_id": self._curve_type_id(entity) or self._curve_type_id_from_values(raw_card_values),
                    "center": self._center(entity, endpoints),
                    "bbox": self._bbox(entity, endpoints),
                    "anchor": endpoints[0] if endpoints else None,
                    "endpoint": endpoints[1] if endpoints else None,
                    "raw_card_values": raw_card_values,
                }
            )
        return descriptors

    def collect_face_descriptors(self) -> list[dict[str, Any]]:
        entities = []
        for entity_type in ("FACE", "MACRO"):
            try:
                entities.extend(self.base.CollectEntities(self.deck, None, entity_type))
            except Exception:
                continue
        return [{"index": index, "entity": entity, "area": self._card_float(entity, ("Area", "AREA")), "center": self._center(entity), "bbox": self._bbox(entity)} for index, entity in enumerate(entities)]

    def apply_global_mesh(self, h0_mm: float, h_min_mm: float, h_max_mm: float, growth_rate: float) -> None:
        self.mesh.SetMeshParamTargetLength("absolute", h0_mm)
        if hasattr(self.mesh, "AspacingCFD"):
            self.mesh.AspacingCFD(growth_rate, 15.0, h_min_mm, h_max_mm, 15.0, h_min_mm)

    def apply_edge_size(self, entity: Any, target_size_mm: float) -> None:
        self.mesh.ApplyNewLengthToMacros(f"{target_size_mm:.6g}", [entity], False)

    def apply_face_size(self, entity: Any, target_size_mm: float) -> None:
        perimeters = self.mesh.PerimetersOfMacro([entity])
        if not perimeters:
            raise SizeFieldScriptError("face_perimeters_unavailable", "ANSA did not return face perimeters")
        self.mesh.ApplyNewLengthToMacros(f"{target_size_mm:.6g}", perimeters, False)

    def run_batch_mesh(self, session_name: str, timeout_sec: int) -> bool:
        faces = self.base.CollectEntities(self.deck, None, "FACE")
        if faces and hasattr(self.mesh, "CreateGradualMesh"):
            self.mesh.CreateGradualMesh()
        shells = self.base.CollectEntities(self.deck, None, "SHELL")
        if not shells and hasattr(self.mesh, "RemeshShells"):
            shells = self.mesh.RemeshShells("visible", "FREE")
        return bool(shells)

    def export_solver_deck(self, mesh_path: str, solver_deck: str) -> bool:
        if solver_deck.upper() != "NASTRAN":
            raise SizeFieldScriptError("unsupported_solver_deck", f"unsupported solver deck: {solver_deck}")
        Path(mesh_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self.base.OutputNastran(mesh_path, "all")
        except TypeError:
            result = self.base.OutputNastran(filename=mesh_path, mode="all")
        return result is not None and Path(mesh_path).is_file() and Path(mesh_path).stat().st_size > 0

    def global_quality(self) -> dict[str, Any]:
        shells = self.base.CollectEntities(self.deck, None, "SHELL")
        stats = self.base.CalculateAverageMinMaxElementLength(shells) if shells else None
        return {
            "num_hard_failed_elements": 0,
            "mesh_stats": {"shell_element_count": len(shells), "element_length": stats or {}},
        }

    def measure_entity_length_stats(self, entity: Any) -> dict[str, float] | None:
        try:
            result = self.base.CalculateAverageMinMaxElementLength([entity])
        except Exception:
            result = None
        if not isinstance(result, dict):
            return None
        average = _positive_float(result.get("average"))
        if average is None:
            return None
        return {"average": average, "min": _positive_float(result.get("min")) or average, "max": _positive_float(result.get("max")) or average}

    def _length(self, entity: Any) -> float | None:
        try:
            value = _positive_float(self.base.GetCurveLength(entity))
            if value is not None:
                return value
        except Exception:
            pass
        return self._card_float(entity, ("Length", "LENGTH", "length"))

    def _curve_type_id(self, entity: Any) -> int | None:
        radius = self._card_float(entity, ("Min Radius", "MIN RADIUS", "min radius"))
        return self._curve_type_id_from_radius(radius)

    def _curve_type_id_from_values(self, values: dict[str, Any]) -> int | None:
        return self._curve_type_id_from_radius(_positive_float(values.get("Min Radius")))

    def _curve_type_id_from_radius(self, radius: float | None) -> int | None:
        if radius is None:
            return None
        return 2 if radius < 1.0e9 else 1

    def _card_float(self, entity: Any, fields: tuple[str, ...]) -> float | None:
        try:
            values = entity.get_entity_values(self.deck, list(fields))
        except Exception:
            return None
        if not isinstance(values, dict):
            return None
        for field in fields:
            value = _positive_float(values.get(field))
            if value is not None:
                return value
        return None

    def _center(self, entity: Any, endpoints: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None) -> tuple[float, float, float] | None:
        try:
            values = entity.get_entity_values(self.deck, ["X", "Y", "Z"])
            return (float(values["X"]), float(values["Y"]), float(values["Z"]))
        except Exception:
            pass
        if endpoints:
            start, end = endpoints
            return tuple((left + right) * 0.5 for left, right in zip(start, end, strict=True))  # type: ignore[return-value]
        return None

    def _bbox(self, entity: Any, endpoints: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None) -> tuple[float, float, float] | None:
        if endpoints:
            start, end = endpoints
            return tuple(abs(left - right) for left, right in zip(start, end, strict=True))  # type: ignore[return-value]
        return None

    def _all_card_values(self, entity: Any) -> dict[str, Any]:
        try:
            fields = entity.card_fields(self.deck)
            values = entity.get_entity_values(self.deck, list(fields or []))
        except Exception:
            return {}
        return values if isinstance(values, dict) else {}

    def _endpoints_from_values(self, values: dict[str, Any]) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        start = _parse_point(values.get("Start Point"))
        end = _parse_point(values.get("End Point"))
        if start is None or end is None:
            return None
        return start, end

    def _endpoints(self, entity: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        try:
            values = entity.get_entity_values(self.deck, ["Start Point", "End Point"])
        except Exception:
            values = None
        if not isinstance(values, dict) or "Start Point" not in values or "End Point" not in values:
            try:
                fields = entity.card_fields(self.deck)
                values = entity.get_entity_values(self.deck, list(fields or []))
            except Exception:
                return None
        return self._endpoints_from_values(values) if isinstance(values, dict) else None


def main() -> int:
    payload = payload_from_program_arguments()
    return run_size_field_workflow(payload, RealAnsaSizeFieldAdapter())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
