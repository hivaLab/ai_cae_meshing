from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.manifest import (
    DeterministicManifestBuildError,
    build_deterministic_amg_manifest,
    load_feature_candidates_from_npz,
    write_deterministic_amg_manifest,
)
from ai_mesh_generator.amg.validation import AmgInputValidationResult, ValidationCheckResult, build_out_of_scope_manifest

ROOT = Path(__file__).resolve().parents[1]
FEATURE_COLUMNS = [
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


def _schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _config() -> dict:
    return json.loads((ROOT / "configs" / "amg_config.default.json").read_text(encoding="utf-8"))


def _case_dir(name: str) -> Path:
    path = ROOT / "runs" / "pytest_tmp_local" / "test_amg_deterministic_manifest" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validation_result(*, accepted: bool = True, overrides: dict | None = None) -> AmgInputValidationResult:
    return AmgInputValidationResult(
        accepted=accepted,
        input_step="cad/input.step",
        config=_config(),
        feature_overrides=overrides,
        checks=[ValidationCheckResult(name="fixture", passed=accepted)],
        failure_manifest=None if accepted else build_out_of_scope_manifest("non_constant_thickness"),
    )


def _graph_schema_doc() -> dict:
    return {
        "schema_version": "AMG_BREP_GRAPH_SM_V1",
        "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
        "edge_types": [
            "PART_HAS_FACE",
            "FACE_HAS_COEDGE",
            "COEDGE_HAS_EDGE",
            "EDGE_HAS_VERTEX",
            "COEDGE_NEXT",
            "COEDGE_PREV",
            "COEDGE_MATE",
            "FACE_ADJACENT_FACE",
            "FEATURE_CONTAINS_FACE",
            "FEATURE_CONTAINS_EDGE",
        ],
        "feature_candidate_columns": FEATURE_COLUMNS,
    }


def _candidate(
    candidate_id: str,
    feature_type: str,
    *,
    role: str = "UNKNOWN",
    radius: float = 0.0,
    width: float = 0.0,
    length: float = 0.0,
    size_1: float = 1.0,
    size_2: float = 1.0,
    mask: int = 0b00101,
    signature: str | None = None,
) -> tuple[list[float], dict]:
    lref = 160.0
    row = [
        {"HOLE": 1, "SLOT": 2, "CUTOUT": 3, "BEND": 4, "FLANGE": 5}[feature_type],
        {"UNKNOWN": 0, "STRUCTURAL": 7}.get(role, 0),
        size_1 / lref,
        size_2 / lref,
        radius / lref,
        width / lref,
        length / lref,
        40.0 / lref,
        50.0 / lref,
        0.0,
        70.0 / lref,
        70.0 / lref,
        1.0,
        mask,
    ]
    metadata = {
        "candidate_id": candidate_id,
        "type": feature_type,
        "role": role,
        "geometry_signature": signature or f"{feature_type}:fixture:{candidate_id}",
        "center_mm": [40.0, 50.0, 0.0],
        "size_1_mm": size_1,
        "size_2_mm": size_2,
        "radius_mm": radius or None,
        "width_mm": width or None,
        "length_mm": length or None,
        "face_node_ids": [1],
        "edge_node_ids": [2, 3],
    }
    return row, metadata


def _write_graph(tmp_path: Path, rows: list[list[float]], metadata: list[dict]) -> tuple[Path, Path]:
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_schema = graph_dir / "graph_schema.json"
    graph_npz = graph_dir / "brep_graph.npz"
    graph_schema.write_text(json.dumps(_graph_schema_doc(), indent=2) + "\n", encoding="utf-8")
    np.savez(
        graph_npz,
        part_features=np.asarray([[0, 0, 0, 0, 160.0, 100.0, 1.2]], dtype=np.float64),
        feature_candidate_features=np.asarray(rows, dtype=np.float64),
        feature_candidate_metadata_json=np.asarray([json.dumps(item, sort_keys=True) for item in metadata]),
    )
    return graph_npz, graph_schema


def _all_feature_graph(tmp_path: Path) -> tuple[Path, Path]:
    pairs = [
        _candidate("DETECTED_HOLE_0001", "HOLE", radius=1.0, size_1=2.0, size_2=2.0, mask=0b00101),
        _candidate("DETECTED_SLOT_0001", "SLOT", width=8.0, length=32.0, size_1=32.0, size_2=8.0, mask=0b00101),
        _candidate("DETECTED_CUTOUT_0001", "CUTOUT", width=24.0, length=16.0, size_1=24.0, size_2=16.0, mask=0b00101),
        _candidate("DETECTED_BEND_0001", "BEND", role="STRUCTURAL", size_1=80.0, size_2=90.0, length=80.0, mask=0b01000),
        _candidate("DETECTED_FLANGE_0001", "FLANGE", role="STRUCTURAL", width=24.0, length=80.0, size_1=80.0, size_2=24.0, mask=0b10000),
    ]
    return _write_graph(tmp_path, [row for row, _ in pairs], [meta for _, meta in pairs])


def test_out_of_scope_validation_result_is_returned_unchanged() -> None:
    failure = _validation_result(accepted=False)

    manifest = build_deterministic_amg_manifest(validation_result=failure, part_class="SM_FLAT_PANEL", candidates=[])

    assert manifest is not failure.failure_manifest
    assert manifest == failure.failure_manifest
    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(manifest)


def test_deterministic_manifest_from_graph_candidates_validates_schema() -> None:
    graph_npz, graph_schema = _all_feature_graph(_case_dir("all_features"))

    manifest = build_deterministic_amg_manifest(
        validation_result=_validation_result(),
        graph_npz_path=graph_npz,
        graph_schema_path=graph_schema,
        part_class="SM_FLAT_PANEL",
    )

    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(manifest)
    assert manifest["status"] == "VALID"
    assert {feature["type"] for feature in manifest["features"]} == {"HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE"}
    assert all("geometry_signature" in feature for feature in manifest["features"])


def test_unknown_hole_is_not_suppressed() -> None:
    row, metadata = _candidate("DETECTED_HOLE_0001", "HOLE", radius=0.3, size_1=0.6, size_2=0.6, mask=0b00101)
    graph_npz, graph_schema = _write_graph(_case_dir("unknown_hole"), [row], [metadata])

    manifest = build_deterministic_amg_manifest(
        validation_result=_validation_result(),
        graph_npz_path=graph_npz,
        graph_schema_path=graph_schema,
        part_class="SM_FLAT_PANEL",
    )

    feature = manifest["features"][0]
    assert feature["role"] == "UNKNOWN"
    assert feature["action"] != "SUPPRESS"


def test_feature_override_promotes_hole_to_washer_control() -> None:
    row, metadata = _candidate(
        "DETECTED_HOLE_0001",
        "HOLE",
        radius=4.0,
        size_1=8.0,
        size_2=8.0,
        mask=0b00111,
        signature="HOLE:fixture:washer",
    )
    graph_npz, graph_schema = _write_graph(_case_dir("washer_override"), [row], [metadata])
    overrides = {
        "schema_version": "AMG_FEATURE_OVERRIDES_SM_V1",
        "features": [
            {
                "feature_id": "HOLE_BOLT_0001",
                "type": "HOLE",
                "role": "BOLT",
                "signature": {"geometry_signature": "HOLE:fixture:washer"},
            }
        ],
    }

    manifest = build_deterministic_amg_manifest(
        validation_result=_validation_result(overrides=overrides),
        graph_npz_path=graph_npz,
        graph_schema_path=graph_schema,
        part_class="SM_FLAT_PANEL",
    )

    feature = manifest["features"][0]
    assert feature["feature_id"] == "HOLE_BOLT_0001"
    assert feature["role"] == "BOLT"
    assert feature["action"] == "KEEP_WITH_WASHER"
    assert feature["controls"]["washer_rings"] == 2


def test_malformed_graph_metadata_raises_structured_error() -> None:
    row, metadata = _candidate("DETECTED_HOLE_0001", "HOLE", radius=2.0, size_1=4.0, size_2=4.0)
    graph_npz, graph_schema = _write_graph(_case_dir("malformed_metadata"), [row, row], [metadata])

    with pytest.raises(DeterministicManifestBuildError) as exc_info:
        load_feature_candidates_from_npz(graph_npz, graph_schema)
    assert exc_info.value.code == "malformed_graph_metadata"


def test_controls_are_bounded_to_mesh_policy() -> None:
    row, metadata = _candidate("DETECTED_SLOT_0001", "SLOT", width=120.0, length=150.0, size_1=150.0, size_2=120.0)
    graph_npz, graph_schema = _write_graph(_case_dir("bounded_controls"), [row], [metadata])

    manifest = build_deterministic_amg_manifest(
        validation_result=_validation_result(),
        graph_npz_path=graph_npz,
        graph_schema_path=graph_schema,
        part_class="SM_FLAT_PANEL",
    )

    controls = manifest["features"][0]["controls"]
    mesh_policy = _config()["mesh_policy"]
    assert mesh_policy["h_min_mm"] <= controls["edge_target_length_mm"] <= mesh_policy["h_max_mm"]
    assert controls["growth_rate"] <= mesh_policy["growth_rate_max"]


def test_missing_part_class_raises_structured_error() -> None:
    graph_npz, graph_schema = _all_feature_graph(_case_dir("missing_part_class"))

    with pytest.raises(DeterministicManifestBuildError) as exc_info:
        build_deterministic_amg_manifest(
            validation_result=_validation_result(),
            graph_npz_path=graph_npz,
            graph_schema_path=graph_schema,
            part_class=None,
        )
    assert exc_info.value.code == "missing_part_class"


def test_write_deterministic_manifest_writes_json() -> None:
    case_dir = _case_dir("write_manifest")
    graph_npz, graph_schema = _all_feature_graph(case_dir)
    manifest = build_deterministic_amg_manifest(
        validation_result=_validation_result(),
        graph_npz_path=graph_npz,
        graph_schema_path=graph_schema,
        part_class="SM_FLAT_PANEL",
    )
    path = case_dir / "labels" / "amg_manifest.json"

    write_deterministic_amg_manifest(path, manifest)

    assert json.loads(path.read_text(encoding="utf-8")) == manifest
