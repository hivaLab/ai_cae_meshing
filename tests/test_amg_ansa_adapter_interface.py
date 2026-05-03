from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.ansa import (
    ManifestRunnerError,
    MockAnsaAdapter,
    RetryPolicy,
    build_manifest_operations,
    build_mesh_failed_manifest,
    deterministic_retry_manifest,
    run_manifest_with_adapter,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_ansa_adapter_interface"


def _case_dir(name: str) -> Path:
    path = RUNS / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_manifest(manifest: dict) -> None:
    schema = json.loads((ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda item: list(item.path))
    assert errors == []


def _manifest() -> dict:
    manifest = {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": "SMT_TEST",
            "part_class": "SM_FLAT_PANEL",
            "idealization": "midsurface_shell",
            "thickness_mm": 1.2,
            "element_type": "quad_dominant_shell",
            "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
        },
        "global_mesh": {
            "h0_mm": 4.0,
            "h_min_mm": 1.2,
            "h_max_mm": 7.2,
            "growth_rate_max": 1.3,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [
            {
                "feature_id": "HOLE_KEEP_0001",
                "type": "HOLE",
                "role": "UNKNOWN",
                "action": "KEEP_REFINED",
                "geometry_signature": {},
                "controls": {
                    "edge_target_length_mm": 4.0,
                    "circumferential_divisions": 12,
                    "radial_growth_rate": 1.25,
                },
            },
            {
                "feature_id": "HOLE_WASHER_0001",
                "type": "HOLE",
                "role": "BOLT",
                "action": "KEEP_WITH_WASHER",
                "geometry_signature": {},
                "controls": {
                    "edge_target_length_mm": 3.5,
                    "circumferential_divisions": 24,
                    "washer_rings": 2,
                    "washer_outer_radius_mm": 6.0,
                    "radial_growth_rate": 1.25,
                },
            },
            {
                "feature_id": "HOLE_SUPPRESS_0001",
                "type": "HOLE",
                "role": "RELIEF",
                "action": "SUPPRESS",
                "geometry_signature": {},
                "controls": {"suppression_rule": "small_relief_or_drain"},
            },
            {
                "feature_id": "SLOT_KEEP_0001",
                "type": "SLOT",
                "role": "UNKNOWN",
                "action": "KEEP_REFINED",
                "geometry_signature": {},
                "controls": {
                    "edge_target_length_mm": 3.0,
                    "end_arc_divisions": 12,
                    "straight_edge_divisions": 4,
                    "growth_rate": 1.2,
                },
            },
            {
                "feature_id": "SLOT_SUPPRESS_0001",
                "type": "SLOT",
                "role": "DRAIN",
                "action": "SUPPRESS",
                "geometry_signature": {},
                "controls": {"suppression_rule": "small_relief_or_drain"},
            },
            {
                "feature_id": "CUTOUT_KEEP_0001",
                "type": "CUTOUT",
                "role": "PASSAGE",
                "action": "KEEP_REFINED",
                "geometry_signature": {},
                "controls": {
                    "edge_target_length_mm": 4.0,
                    "perimeter_growth_rate": 1.2,
                },
            },
            {
                "feature_id": "BEND_STRUCTURAL_0001",
                "type": "BEND",
                "role": "STRUCTURAL",
                "action": "KEEP_WITH_BEND_ROWS",
                "geometry_signature": {},
                "controls": {
                    "bend_rows": 2,
                    "bend_target_length_mm": 2.0,
                    "growth_rate": 1.2,
                },
            },
            {
                "feature_id": "FLANGE_STRUCTURAL_0001",
                "type": "FLANGE",
                "role": "STRUCTURAL",
                "action": "KEEP_WITH_FLANGE_SIZE",
                "geometry_signature": {},
                "controls": {
                    "flange_target_length_mm": 4.0,
                    "min_elements_across_width": 2,
                },
            },
        ],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }
    _validate_manifest(manifest)
    return manifest


def test_manifest_builds_deterministic_adapter_operations() -> None:
    operations = build_manifest_operations(_manifest())
    names = [operation.name for operation in operations]

    assert names[:8] == [
        "import_step",
        "run_geometry_cleanup",
        "extract_midsurface",
        "assign_thickness",
        "build_entity_index",
        "match_entities",
        "create_sets",
        "assign_batch_session",
    ]
    assert names.count("apply_edge_length") == 3
    assert "apply_hole_washer" in names
    assert names.count("fill_hole") == 2
    assert "apply_bend_rows" in names
    assert "apply_flange_size" in names
    assert names[-1] == "run_batch_mesh"


def test_all_canonical_feature_actions_map_to_expected_adapter_methods() -> None:
    operations = build_manifest_operations(_manifest())
    by_first_arg = {
        operation.args[0]: operation.name
        for operation in operations
        if operation.name.startswith("apply_") or operation.name == "fill_hole"
    }

    assert by_first_arg["EDGE_SET_HOLE_KEEP_0001"] == "apply_edge_length"
    assert by_first_arg["FEATURE_SET_HOLE_WASHER_0001"] == "apply_hole_washer"
    assert by_first_arg["FEATURE_SET_HOLE_SUPPRESS_0001"] == "fill_hole"
    assert by_first_arg["EDGE_SET_SLOT_KEEP_0001"] == "apply_edge_length"
    assert by_first_arg["FEATURE_SET_SLOT_SUPPRESS_0001"] == "fill_hole"
    assert by_first_arg["EDGE_SET_CUTOUT_KEEP_0001"] == "apply_edge_length"
    assert by_first_arg["FEATURE_SET_BEND_STRUCTURAL_0001"] == "apply_bend_rows"
    assert by_first_arg["FEATURE_SET_FLANGE_STRUCTURAL_0001"] == "apply_flange_size"


def test_dry_run_does_not_call_adapter() -> None:
    adapter = MockAnsaAdapter()
    result = run_manifest_with_adapter(_manifest(), adapter, _case_dir("dry_run"), dry_run=True)

    assert result.status == "DRY_RUN"
    assert result.operations
    assert adapter.operation_log == []


def test_mock_adapter_success_writes_quality_report_and_solver_deck() -> None:
    adapter = MockAnsaAdapter()
    result = run_manifest_with_adapter(_manifest(), adapter, _case_dir("success"))

    assert result.status == "COMPLETED"
    assert result.attempts == 1
    assert result.quality_report_path is not None
    assert result.solver_deck_path is not None
    quality = json.loads(Path(result.quality_report_path).read_text(encoding="utf-8"))
    assert quality["schema"] == "CDF_ANSA_QUALITY_REPORT_SM_V1"
    assert quality["accepted"] is True
    assert Path(result.solver_deck_path).read_text(encoding="utf-8").startswith("mock solver deck")


def test_configured_adapter_failure_returns_structured_failed_result() -> None:
    adapter = MockAnsaAdapter(fail_on_operation="run_batch_mesh")
    result = run_manifest_with_adapter(_manifest(), adapter, _case_dir("failure"))

    assert result.status == "FAILED"
    assert result.error_code == "mock_operation_failed"
    assert "run_batch_mesh" in (result.message or "")


def test_retry_policy_cases_mutate_manifest_deterministically() -> None:
    manifest = _manifest()

    hole_retry = deterministic_retry_manifest(manifest, "hole_perimeter_quality_fail")
    assert hole_retry["features"][0]["controls"]["edge_target_length_mm"] == 3.0

    bend_retry = deterministic_retry_manifest(manifest, "bend_warpage_skew_fail")
    assert bend_retry["features"][6]["controls"]["bend_rows"] == 3

    flange_retry = deterministic_retry_manifest(manifest, "flange_narrow_face_fail")
    assert flange_retry["features"][7]["controls"]["flange_target_length_mm"] == 3.2

    global_retry = deterministic_retry_manifest(manifest, "global_growth_fail")
    assert global_retry["global_mesh"]["growth_rate_max"] == 1.2


def test_retry_exhaustion_returns_mesh_failed_manifest() -> None:
    adapter = MockAnsaAdapter(
        quality_outcomes=(False, False, False),
        retry_cases=("global_growth_fail", "global_growth_fail", "global_growth_fail"),
    )
    result = run_manifest_with_adapter(_manifest(), adapter, _case_dir("retry_exhausted"), retry_policy=RetryPolicy(max_attempts=2))

    assert result.status == "MESH_FAILED"
    assert result.attempts == 3
    assert result.failure_manifest == build_mesh_failed_manifest()
    _validate_manifest(result.failure_manifest)


def test_malformed_manifest_and_unsupported_action_raise() -> None:
    malformed = deepcopy(_manifest())
    del malformed["status"]
    with pytest.raises(ManifestRunnerError) as schema_exc:
        build_manifest_operations(malformed)
    assert schema_exc.value.code == "manifest_schema_invalid"

    unsupported = deepcopy(_manifest())
    unsupported["features"][5]["action"] = "SUPPRESS"
    with pytest.raises(ManifestRunnerError) as unsupported_exc:
        build_manifest_operations(unsupported)
    assert unsupported_exc.value.code == "unsupported_manifest_action"


def test_unsupported_retry_case_raises() -> None:
    with pytest.raises(ManifestRunnerError) as exc_info:
        deterministic_retry_manifest(_manifest(), "unknown_retry_case")

    assert exc_info.value.code == "unsupported_retry_case"
