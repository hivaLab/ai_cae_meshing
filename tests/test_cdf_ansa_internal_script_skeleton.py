from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.oracle.ansa_scripts import cdf_ansa_api_layer, cdf_ansa_oracle

ROOT = Path(__file__).resolve().parents[1]


def _sample_dir(name: str = "sample_000402", *, with_manifest: bool = True) -> Path:
    sample_dir = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_internal_script_skeleton" / "samples" / name
    labels_dir = sample_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    manifest = labels_dir / "amg_manifest.json"
    if with_manifest:
        manifest.write_text('{"schema_version":"AMG_MANIFEST_SM_V1","status":"VALID"}\n', encoding="utf-8")
    elif manifest.exists():
        manifest.unlink()
    return sample_dir


def _argv(sample_dir: Path) -> list[str]:
    return [
        "--sample-dir",
        sample_dir.as_posix(),
        "--manifest",
        (sample_dir / "labels" / "amg_manifest.json").as_posix(),
        "--execution-report",
        (sample_dir / "reports" / "ansa_execution_report.json").as_posix(),
        "--quality-report",
        (sample_dir / "reports" / "ansa_quality_report.json").as_posix(),
        "--batch-mesh-session",
        "AMG_SHELL_CONST_THICKNESS_V1",
        "--quality-profile",
        "AMG_QA_SHELL_V1",
        "--solver-deck",
        "NASTRAN",
        "--save-ansa-database",
        "true",
    ]


def _load_execution_report(sample_dir: Path) -> dict:
    return json.loads((sample_dir / "reports" / "ansa_execution_report.json").read_text(encoding="utf-8"))


def test_parse_args_reads_t401_command_flags() -> None:
    sample_dir = _sample_dir()

    args = cdf_ansa_oracle.parse_args(_argv(sample_dir))

    assert args.sample_dir == sample_dir.as_posix()
    assert args.manifest.endswith("amg_manifest.json")
    assert args.execution_report.endswith("ansa_execution_report.json")
    assert args.quality_report.endswith("ansa_quality_report.json")
    assert args.batch_mesh_session == "AMG_SHELL_CONST_THICKNESS_V1"
    assert args.quality_profile == "AMG_QA_SHELL_V1"
    assert args.solver_deck == "NASTRAN"
    assert args.save_ansa_database == "true"


def test_main_writes_schema_valid_controlled_failure_report() -> None:
    sample_dir = _sample_dir()

    exit_code = cdf_ansa_oracle.main(_argv(sample_dir))

    assert exit_code == cdf_ansa_oracle.CONTROLLED_FAILURE_EXIT_CODE
    report = _load_execution_report(sample_dir)
    schema = json.loads((ROOT / "contracts" / "CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)
    assert report["sample_id"] == sample_dir.name
    assert report["accepted"] is False
    assert report["step_import_success"] is False
    assert report["midsurface_extraction_success"] is False
    assert report["feature_matching_success"] is False
    assert report["batch_mesh_success"] is False
    assert report["solver_export_success"] is False
    assert report["outputs"]["controlled_failure_reason"] == "ansa_api_unavailable"


def test_missing_manifest_still_writes_execution_report() -> None:
    sample_dir = _sample_dir("sample_000403", with_manifest=False)

    exit_code = cdf_ansa_oracle.main(_argv(sample_dir))

    assert exit_code == cdf_ansa_oracle.CONTROLLED_FAILURE_EXIT_CODE
    report = _load_execution_report(sample_dir)
    assert report["accepted"] is False
    assert report["outputs"]["controlled_failure_reason"] == "missing_manifest"


def test_api_layer_placeholder_functions_raise_unavailable() -> None:
    with pytest.raises(cdf_ansa_api_layer.AnsaApiUnavailable) as exc_info:
        cdf_ansa_api_layer.ansa_import_step("input.step")
    assert exc_info.value.operation == "ansa_import_step"

    with pytest.raises(cdf_ansa_api_layer.AnsaApiUnavailable) as exc_info:
        cdf_ansa_api_layer.ansa_run_batch_mesh(cdf_ansa_api_layer.AnsaModelRef(handle=None), "SESSION")
    assert exc_info.value.operation == "ansa_run_batch_mesh"


class _FakeControlMesh:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def SetMeshParamTargetLength(self, function: str, value: float) -> int:
        self.calls.append(("SetMeshParamTargetLength", (function, value)))
        return 1

    def ApplyNewLengthToMacros(self, element_length: str, perimeters: int, use_ansa_defaults_values: bool) -> int:
        self.calls.append(("ApplyNewLengthToMacros", (element_length, perimeters, use_ansa_defaults_values)))
        return 0

    def NumberPerimeters(
        self,
        input_entities: int,
        number: str,
        apply_multiple_number: bool,
        remesh_macros: bool,
        apply_number_of: str,
        use_ansa_defaults_values: bool,
    ) -> int:
        self.calls.append(("NumberPerimeters", (input_entities, number, apply_multiple_number, remesh_macros, apply_number_of, use_ansa_defaults_values)))
        return 1

    def CreateCircularMesh(
        self,
        entities: int,
        only_circular: bool,
        only_even: bool,
        radius_tol: float,
        pattern: str,
        zones: int,
        layers: int,
        first_height: float,
        growth_factor: float,
        max_aspect: float,
    ) -> object:
        self.calls.append(("CreateCircularMesh", (entities, only_circular, only_even, radius_tol, pattern, zones, layers, first_height, growth_factor, max_aspect)))
        return SimpleNamespace(meshed_ents=[object()])

    def FillSingleBoundHoles(
        self,
        max_diameter: float,
        fill_ext_perim: bool,
        point_at_center: bool,
        connection_by: str,
        curve_at_perimeter: bool,
        reshape_zones: int,
        set_id: object,
        pid_id: object,
        ret_ents: bool,
        fill_method: str,
        part: object,
        geom_fill_method: str,
    ) -> list[object]:
        self.calls.append(("FillSingleBoundHoles", (max_diameter, fill_ext_perim, point_at_center, connection_by, curve_at_perimeter, reshape_zones, set_id, pid_id, ret_ents, fill_method, part, geom_fill_method)))
        return [object()]


class _FakeControlBase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def BCSettingsSetValues(self, fields: dict) -> int:
        self.calls.append(("BCSettingsSetValues", fields))
        return 1


class _FakeControlBatchmesh:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, dict]] = []

    def SetSessionParameters(self, session: object, fields: dict) -> int:
        self.calls.append(("SetSessionParameters", session, fields))
        return 1


def _fake_control_model() -> tuple[cdf_ansa_api_layer.AnsaModelRef, _FakeControlMesh, _FakeControlBase, _FakeControlBatchmesh]:
    fake_mesh = _FakeControlMesh()
    fake_base = _FakeControlBase()
    fake_batchmesh = _FakeControlBatchmesh()
    modules = SimpleNamespace(
        mesh=fake_mesh,
        base=fake_base,
        batchmesh=fake_batchmesh,
        constants=SimpleNamespace(NASTRAN="NASTRAN"),
    )
    return cdf_ansa_api_layer.AnsaModelRef(handle={}, modules=modules, session=object()), fake_mesh, fake_base, fake_batchmesh


def test_real_control_binding_calls_ansa_mesh_apis_for_washer_hole() -> None:
    model, fake_mesh, fake_base, fake_batchmesh = _fake_control_model()
    controls = {
        "edge_target_length_mm": 2.5,
        "circumferential_divisions": 16,
        "washer_rings": 2,
        "radial_growth_rate": 1.2,
    }
    feature = {"feature_id": "HOLE_BOLT_0001", "type": "HOLE", "action": "KEEP_WITH_WASHER"}

    report = cdf_ansa_api_layer.ansa_apply_hole_control(model, controls, feature)

    call_names = [name for name, _args in fake_mesh.calls]
    assert report["bound_to_real_ansa_api"] is True
    assert set(report["successful_control_paths"]) >= {"mesh_length", "perimeter_divisions", "washer"}
    assert "SetMeshParamTargetLength" in call_names
    assert "ApplyNewLengthToMacros" in call_names
    assert "NumberPerimeters" in call_names
    assert "CreateCircularMesh" in call_names
    assert fake_base.calls
    assert fake_batchmesh.calls


def test_real_control_binding_calls_fill_for_suppression() -> None:
    model, fake_mesh, _fake_base, _fake_batchmesh = _fake_control_model()
    controls = {"suppression_rule": "quality_exploration_action_swap"}
    feature = {
        "feature_id": "HOLE_RELIEF_0001",
        "type": "HOLE",
        "action": "SUPPRESS",
        "geometry_signature": {"geometry_signature": "HOLE:12.0:15.0:4.0:4.0"},
    }

    report = cdf_ansa_api_layer.ansa_apply_hole_control(model, controls, feature)

    assert report["bound_to_real_ansa_api"] is True
    assert report["successful_control_paths"] == ["suppression"]
    fill_calls = [args for name, args in fake_mesh.calls if name == "FillSingleBoundHoles"]
    assert fill_calls
    assert fill_calls[0][0] == pytest.approx(4.0)
