"""Deterministic AMG manifest generation from B-rep feature candidates."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.validation import AmgInputValidationResult
from ai_mesh_generator.labels.rule_manifest import (
    KEEP_REFINED,
    KEEP_WITH_BEND_ROWS,
    KEEP_WITH_FLANGE_SIZE,
    KEEP_WITH_WASHER,
    SUPPRESS,
    bend_rule,
    cutout_rule,
    flange_rule,
    hole_rule,
    slot_rule,
)

MANIFEST_SCHEMA = "AMG_MANIFEST_SM_V1"
GRAPH_SCHEMA = "AMG_BREP_GRAPH_SM_V1"
FEATURE_CANDIDATE_COLUMNS = [
    "feature_type_id",
    "role_id",
    "size_1_over_Lref",
    "size_2_over_Lref",
    "radius_over_Lref",
    "width_over_Lref",
    "length_over_Lref",
    "center_x_over_Lref",
    "center_y_over_Lref",
    "center_z_over_Lref",
    "distance_to_outer_boundary_over_Lref",
    "distance_to_nearest_feature_over_Lref",
    "clearance_ratio",
    "expected_action_mask",
]
ACTION_BITS = {
    KEEP_REFINED: 0b00001,
    KEEP_WITH_WASHER: 0b00010,
    SUPPRESS: 0b00100,
    KEEP_WITH_BEND_ROWS: 0b01000,
    KEEP_WITH_FLANGE_SIZE: 0b10000,
}
PART_CLASSES = {
    "SM_FLAT_PANEL",
    "SM_SINGLE_FLANGE",
    "SM_L_BRACKET",
    "SM_U_CHANNEL",
    "SM_HAT_CHANNEL",
}


class DeterministicManifestBuildError(ValueError):
    """Raised when a rule-only manifest cannot be generated safely."""

    def __init__(self, code: str, message: str, candidate_id: str | None = None) -> None:
        self.code = code
        self.candidate_id = candidate_id
        prefix = code if candidate_id is None else f"{code} [{candidate_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class FeatureCandidateRecord:
    candidate_id: str
    type: str
    role: str
    geometry_signature: str
    center_mm: tuple[float, float, float]
    size_1_mm: float
    size_2_mm: float
    radius_mm: float | None
    width_mm: float | None
    length_mm: float | None
    distance_to_outer_boundary_mm: float
    distance_to_nearest_feature_mm: float
    clearance_ratio: float
    expected_action_mask: int
    face_node_ids: tuple[int, ...]
    edge_node_ids: tuple[int, ...]
    part_bbox_mm: tuple[float, float, float]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeterministicManifestBuildError("json_read_failed", f"could not read {path}") from exc
    except json.JSONDecodeError as exc:
        raise DeterministicManifestBuildError("json_parse_failed", f"could not parse {path}") from exc
    if not isinstance(loaded, dict):
        raise DeterministicManifestBuildError("json_document_not_object", f"{path} must contain a JSON object")
    return loaded


def _jsonable_dict(value: Mapping[str, Any], *, code: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise DeterministicManifestBuildError(code, "document must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise DeterministicManifestBuildError(code, "document must be a JSON object")
    return normalized


def _schema(name: str) -> dict[str, Any]:
    return _read_json(_repo_root() / "contracts" / f"{name}.schema.json")


def _validate_schema(document: dict[str, Any], schema_name: str, *, code: str) -> None:
    validator = Draft202012Validator(_schema(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise DeterministicManifestBuildError(code, f"{schema_name} {location}: {first.message}")


def _load_graph_schema(graph_schema_path: str | Path) -> dict[str, Any]:
    graph_schema = _read_json(Path(graph_schema_path))
    _validate_schema(graph_schema, GRAPH_SCHEMA, code="invalid_graph_schema")
    columns = graph_schema.get("feature_candidate_columns")
    if columns != FEATURE_CANDIDATE_COLUMNS:
        raise DeterministicManifestBuildError(
            "unsupported_graph_schema",
            "feature_candidate_columns must match AMG_BREP_GRAPH_SM_V1 canonical order",
        )
    return graph_schema


def _metadata_items(raw: np.ndarray, expected_count: int) -> list[dict[str, Any]]:
    if raw.shape[0] != expected_count:
        raise DeterministicManifestBuildError("malformed_graph_metadata", "candidate metadata count must match feature rows")
    metadata: list[dict[str, Any]] = []
    try:
        for item in raw.tolist():
            loaded = json.loads(str(item))
            if not isinstance(loaded, dict):
                raise ValueError("metadata item is not an object")
            metadata.append(loaded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DeterministicManifestBuildError("malformed_graph_metadata", "candidate metadata must be JSON objects") from exc
    return metadata


def _tuple3(value: Any, *, code: str, candidate_id: str) -> tuple[float, float, float]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise DeterministicManifestBuildError(code, "center_mm must be a 3-vector", candidate_id)
    return (float(value[0]), float(value[1]), float(value[2]))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _int_tuple(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        return ()
    return tuple(int(item) for item in value)


def load_feature_candidates_from_npz(
    graph_npz_path: str | Path,
    graph_schema_path: str | Path,
) -> list[FeatureCandidateRecord]:
    """Load AMG feature candidate records from B-rep graph contract files."""

    _load_graph_schema(graph_schema_path)
    try:
        loaded = np.load(Path(graph_npz_path), allow_pickle=False)
    except OSError as exc:
        raise DeterministicManifestBuildError("graph_npz_read_failed", f"could not read graph npz: {graph_npz_path}") from exc
    with loaded:
        required = {"part_features", "feature_candidate_features", "feature_candidate_metadata_json"}
        missing = sorted(required - set(loaded.files))
        if missing:
            raise DeterministicManifestBuildError("missing_graph_array", f"missing graph arrays: {', '.join(missing)}")
        part_features = loaded["part_features"]
        feature_rows = loaded["feature_candidate_features"]
        if part_features.shape[0] != 1 or part_features.shape[1] < 7:
            raise DeterministicManifestBuildError("malformed_graph_array", "part_features must have one row with bbox columns")
        if feature_rows.ndim != 2 or feature_rows.shape[1] != len(FEATURE_CANDIDATE_COLUMNS):
            raise DeterministicManifestBuildError("malformed_graph_array", "feature_candidate_features has invalid shape")
        metadata = _metadata_items(loaded["feature_candidate_metadata_json"], feature_rows.shape[0])

    part_bbox = tuple(float(value) for value in part_features[0, 4:7])
    lref = max(part_bbox)
    if lref <= 0.0:
        raise DeterministicManifestBuildError("invalid_reference_length", "part bbox must define a positive Lref")

    records: list[FeatureCandidateRecord] = []
    seen: set[str] = set()
    for row, item in zip(feature_rows, metadata, strict=True):
        candidate_id = item.get("candidate_id")
        feature_type = item.get("type")
        role = item.get("role", "UNKNOWN")
        geometry_signature = item.get("geometry_signature")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise DeterministicManifestBuildError("malformed_graph_metadata", "candidate_id is required")
        if candidate_id in seen:
            raise DeterministicManifestBuildError("duplicate_candidate_id", "candidate ids must be unique", candidate_id)
        seen.add(candidate_id)
        if feature_type not in {"HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE"}:
            raise DeterministicManifestBuildError("unsupported_feature_type", "candidate type is not supported", candidate_id)
        if not isinstance(role, str) or not role:
            raise DeterministicManifestBuildError("unsupported_feature_role", "candidate role must be a string", candidate_id)
        if not isinstance(geometry_signature, str) or not geometry_signature:
            raise DeterministicManifestBuildError("malformed_graph_metadata", "geometry_signature is required", candidate_id)
        records.append(
            FeatureCandidateRecord(
                candidate_id=candidate_id,
                type=feature_type,
                role=role,
                geometry_signature=geometry_signature,
                center_mm=_tuple3(item.get("center_mm"), code="malformed_graph_metadata", candidate_id=candidate_id),
                size_1_mm=float(item.get("size_1_mm", row[2] * lref)),
                size_2_mm=float(item.get("size_2_mm", row[3] * lref)),
                radius_mm=_optional_float(item.get("radius_mm")) or (float(row[4]) * lref if row[4] > 0.0 else None),
                width_mm=_optional_float(item.get("width_mm")) or (float(row[5]) * lref if row[5] > 0.0 else None),
                length_mm=_optional_float(item.get("length_mm")) or (float(row[6]) * lref if row[6] > 0.0 else None),
                distance_to_outer_boundary_mm=float(row[10]) * lref,
                distance_to_nearest_feature_mm=float(row[11]) * lref,
                clearance_ratio=float(row[12]),
                expected_action_mask=int(row[13]),
                face_node_ids=_int_tuple(item.get("face_node_ids")),
                edge_node_ids=_int_tuple(item.get("edge_node_ids")),
                part_bbox_mm=part_bbox,
            )
        )
    return records


def _override_map(feature_overrides: Mapping[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_signature: dict[str, dict[str, Any]] = {}
    if not feature_overrides:
        return by_id, by_signature
    overrides = _jsonable_dict(feature_overrides, code="malformed_feature_overrides")
    for item in overrides.get("features", []):
        if not isinstance(item, dict):
            continue
        feature_id = item.get("feature_id")
        if isinstance(feature_id, str):
            by_id[feature_id] = item
        signature = item.get("signature")
        if isinstance(signature, dict) and isinstance(signature.get("geometry_signature"), str):
            by_signature[signature["geometry_signature"]] = item
    return by_id, by_signature


def _apply_override(candidate: FeatureCandidateRecord, override: Mapping[str, Any] | None) -> tuple[str, str, str]:
    if override is None:
        return candidate.candidate_id, candidate.type, candidate.role
    return (
        str(override.get("feature_id", candidate.candidate_id)),
        str(override.get("type", candidate.type)),
        str(override.get("role", candidate.role)),
    )


def _project_action(action: str, controls: dict[str, Any], candidate: FeatureCandidateRecord, role: str) -> tuple[str, dict[str, Any]]:
    if role == "UNKNOWN" and action == SUPPRESS:
        return KEEP_REFINED, {}
    bit = ACTION_BITS.get(action)
    if bit is not None and candidate.expected_action_mask and not (candidate.expected_action_mask & bit):
        if candidate.expected_action_mask & ACTION_BITS[KEEP_REFINED]:
            return KEEP_REFINED, {}
        raise DeterministicManifestBuildError("action_mask_rejected", "rule action is not allowed by candidate mask", candidate.candidate_id)
    return action, controls


def _bounded_controls(controls: Mapping[str, Any], mesh_policy: Mapping[str, Any]) -> dict[str, Any]:
    h_min = float(mesh_policy["h_min_mm"])
    h_max = float(mesh_policy["h_max_mm"])
    growth_max = float(mesh_policy["growth_rate_max"])
    bounded: dict[str, Any] = {}
    for key, value in controls.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            bounded[key] = value
            continue
        numeric = float(value)
        if key.endswith("target_length_mm") or key == "edge_target_length_mm":
            numeric = min(max(numeric, h_min), h_max)
        elif "growth_rate" in key:
            numeric = min(numeric, growth_max)
        bounded[key] = int(numeric) if isinstance(value, int) and numeric.is_integer() else numeric
    return bounded


def _midsurface_area(candidate: FeatureCandidateRecord) -> float:
    dims = sorted((value for value in candidate.part_bbox_mm if value > 0.0), reverse=True)
    return dims[0] * dims[1] if len(dims) >= 2 else 1.0


def _rule_for_candidate(
    candidate: FeatureCandidateRecord,
    *,
    role: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    mesh_policy = dict(config["mesh_policy"])
    feature_policy = dict(config["feature_policy"])
    thickness_mm = float(config["thickness_mm"])
    if candidate.type == "HOLE":
        radius = candidate.radius_mm or candidate.size_1_mm / 2.0
        boundary_clearance = (
            candidate.distance_to_outer_boundary_mm
            if candidate.distance_to_outer_boundary_mm > 0.0
            else math.inf
        )
        feature_clearance = (
            candidate.distance_to_nearest_feature_mm
            if candidate.distance_to_nearest_feature_mm > 0.0
            else math.inf
        )
        return hole_rule(
            radius_mm=radius,
            role=role,
            thickness_mm=thickness_mm,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
            clearance_to_boundary_mm=boundary_clearance,
            clearance_to_nearest_feature_mm=feature_clearance,
        )
    if candidate.type == "SLOT":
        width = candidate.width_mm or candidate.size_2_mm
        length = candidate.length_mm or candidate.size_1_mm
        return slot_rule(
            width_mm=width,
            length_mm=length,
            role=role,
            thickness_mm=thickness_mm,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
        )
    if candidate.type == "CUTOUT":
        width = candidate.width_mm or candidate.size_1_mm
        height = candidate.length_mm or candidate.size_2_mm
        return cutout_rule(
            width_mm=width,
            height_mm=height,
            area_mm2=width * height,
            midsurface_area_mm2=_midsurface_area(candidate),
            role=role,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
        )
    if candidate.type == "BEND":
        return bend_rule(
            inner_radius_mm=candidate.radius_mm or thickness_mm,
            angle_deg=candidate.size_2_mm,
            thickness_mm=thickness_mm,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
        )
    if candidate.type == "FLANGE":
        return flange_rule(
            width_mm=candidate.width_mm or candidate.size_2_mm,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
        )
    raise DeterministicManifestBuildError("unsupported_feature_type", "candidate type is not supported", candidate.candidate_id)


def _feature_record(
    candidate: FeatureCandidateRecord,
    *,
    feature_id: str,
    role: str,
    rule_result: Mapping[str, Any],
    mesh_policy: Mapping[str, Any],
) -> dict[str, Any]:
    action, controls = _project_action(str(rule_result["action"]), dict(rule_result.get("controls", {})), candidate, role)
    controls = _bounded_controls(controls, mesh_policy)
    record = {
        "feature_id": feature_id,
        "type": candidate.type,
        "role": role,
        "action": action,
        "geometry_signature": {
            "candidate_id": candidate.candidate_id,
            "geometry_signature": candidate.geometry_signature,
            "face_node_ids": list(candidate.face_node_ids),
            "edge_node_ids": list(candidate.edge_node_ids),
        },
        "controls": controls,
    }
    if "suppression_rule" in controls:
        record["suppression_rule"] = str(controls["suppression_rule"])
    return record


def _manifest_from_records(
    *,
    validation_result: AmgInputValidationResult,
    part_class: str,
    records: list[dict[str, Any]],
    cad_file: str | None,
) -> dict[str, Any]:
    config = validation_result.config
    mesh_policy = config["mesh_policy"]
    return {
        "schema_version": MANIFEST_SCHEMA,
        "status": "VALID",
        "cad_file": cad_file or validation_result.input_step,
        "unit": "mm",
        "part": {
            "part_name": config["part_name"],
            "part_class": part_class,
            "idealization": "midsurface_shell",
            "thickness_mm": config["thickness_mm"],
            "element_type": mesh_policy["element_type"],
            "batch_session": config["ansa"]["batch_session"],
        },
        "global_mesh": {
            "h0_mm": mesh_policy["h0_mm"],
            "h_min_mm": mesh_policy["h_min_mm"],
            "h_max_mm": mesh_policy["h_max_mm"],
            "growth_rate_max": mesh_policy["growth_rate_max"],
            "quality_profile": config["quality_profile"],
        },
        "features": records,
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def build_deterministic_amg_manifest(
    *,
    validation_result: AmgInputValidationResult,
    part_class: str | None,
    graph_npz_path: str | Path | None = None,
    graph_schema_path: str | Path | None = None,
    candidates: Sequence[FeatureCandidateRecord] | None = None,
    feature_overrides: Mapping[str, Any] | None = None,
    cad_file: str | None = None,
) -> dict[str, Any]:
    """Build an AMG_MANIFEST_SM_V1 manifest with deterministic rule-only controls."""

    if not validation_result.accepted:
        if validation_result.failure_manifest is None:
            raise DeterministicManifestBuildError("missing_failure_manifest", "invalid inputs require a failure manifest")
        return dict(validation_result.failure_manifest)
    if part_class is None:
        raise DeterministicManifestBuildError("missing_part_class", "part_class must be supplied explicitly")
    if part_class not in PART_CLASSES:
        raise DeterministicManifestBuildError("unsupported_part_class", "part_class is not canonical")
    if candidates is None:
        if graph_npz_path is None or graph_schema_path is None:
            raise DeterministicManifestBuildError("missing_graph_inputs", "graph npz and graph schema paths are required")
        candidates = load_feature_candidates_from_npz(graph_npz_path, graph_schema_path)

    override_source = feature_overrides if feature_overrides is not None else validation_result.feature_overrides
    overrides_by_id, overrides_by_signature = _override_map(override_source)
    records: list[dict[str, Any]] = []
    seen_feature_ids: set[str] = set()
    for candidate in candidates:
        override = overrides_by_id.get(candidate.candidate_id) or overrides_by_signature.get(candidate.geometry_signature)
        feature_id, feature_type, role = _apply_override(candidate, override)
        if feature_type != candidate.type:
            raise DeterministicManifestBuildError("override_type_mismatch", "feature override type must match detected candidate type", candidate.candidate_id)
        if feature_id in seen_feature_ids:
            raise DeterministicManifestBuildError("duplicate_feature_id", "manifest feature ids must be unique", candidate.candidate_id)
        seen_feature_ids.add(feature_id)
        rule_result = _rule_for_candidate(candidate, role=role, config=validation_result.config)
        records.append(
            _feature_record(
                candidate,
                feature_id=feature_id,
                role=role,
                rule_result=rule_result,
                mesh_policy=validation_result.config["mesh_policy"],
            )
        )

    manifest = _manifest_from_records(
        validation_result=validation_result,
        part_class=part_class,
        records=records,
        cad_file=cad_file,
    )
    _validate_schema(manifest, MANIFEST_SCHEMA, code="manifest_schema_invalid")
    return manifest


def write_deterministic_amg_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    normalized = _jsonable_dict(manifest, code="malformed_manifest")
    _validate_schema(normalized, MANIFEST_SCHEMA, code="manifest_schema_invalid")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
