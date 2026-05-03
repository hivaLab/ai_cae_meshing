from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import ai_mesh_generator.amg.validation.input_validation as input_validation
from ai_mesh_generator.amg.validation import (
    AmgInputValidationError,
    build_out_of_scope_manifest,
    validate_amg_inputs,
    write_out_of_scope_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _default_config() -> dict:
    return json.loads((ROOT / "configs" / "amg_config.default.json").read_text(encoding="utf-8"))


def _fake_step(name: str = "input.step") -> Path:
    path = ROOT / "runs" / "pytest_tmp_local" / "test_amg_input_validation" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return path


def _valid_overrides() -> dict:
    return {
        "schema_version": "AMG_FEATURE_OVERRIDES_SM_V1",
        "features": [
            {
                "feature_id": "HOLE_BOLT_0001",
                "type": "HOLE",
                "role": "BOLT",
                "signature": {
                    "center_mm": [42.0, 30.0, 0.0],
                    "axis": [0.0, 0.0, 1.0],
                    "radius_mm": 3.2,
                    "tolerance_mm": 0.05,
                },
            }
        ],
    }


def test_default_config_validates_in_t501_path_without_cad_kernel() -> None:
    result = validate_amg_inputs(
        input_step=_fake_step(),
        amg_config=ROOT / "configs" / "amg_config.default.json",
        run_geometry_checks=False,
    )

    assert result.accepted is True
    assert result.failure_manifest is None
    assert result.config["schema_version"] == "AMG_CONFIG_SM_V1"
    assert [check.name for check in result.checks][-1] == "geometry_checks_skipped"


def test_malformed_amg_config_raises_structured_error() -> None:
    config = _default_config()
    config.pop("unit")

    with pytest.raises(AmgInputValidationError) as exc_info:
        validate_amg_inputs(input_step=_fake_step(), amg_config=config, run_geometry_checks=False)

    assert exc_info.value.code == "invalid_amg_config"
    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(exc_info.value.manifest)


def test_feature_overrides_schema_validation() -> None:
    result = validate_amg_inputs(
        input_step=_fake_step(),
        amg_config=_default_config(),
        feature_overrides=_valid_overrides(),
        run_geometry_checks=False,
    )

    assert result.accepted is True
    assert result.feature_overrides is not None
    assert result.feature_overrides["schema_version"] == "AMG_FEATURE_OVERRIDES_SM_V1"

    invalid = _valid_overrides()
    invalid["features"][0]["role"] = "NOT_A_ROLE"
    with pytest.raises(AmgInputValidationError) as exc_info:
        validate_amg_inputs(
            input_step=_fake_step(),
            amg_config=_default_config(),
            feature_overrides=invalid,
            run_geometry_checks=False,
        )
    assert exc_info.value.code == "invalid_feature_overrides"


def test_missing_input_step_returns_out_of_scope_manifest() -> None:
    missing = ROOT / "runs" / "pytest_tmp_local" / "test_amg_input_validation" / "missing.step"

    result = validate_amg_inputs(input_step=missing, amg_config=_default_config(), run_geometry_checks=False)

    assert result.accepted is False
    assert result.failure_manifest == {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "OUT_OF_SCOPE",
        "reason": "input_step_not_found",
    }
    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(result.failure_manifest)


def test_out_of_scope_manifest_helper_and_writer_validate_schema() -> None:
    manifest = build_out_of_scope_manifest("non_constant_thickness", "ignored by the schema")
    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(manifest)

    path = ROOT / "runs" / "pytest_tmp_local" / "test_amg_input_validation" / "manifest.json"
    write_out_of_scope_manifest(path, manifest)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == manifest


def test_cadquery_unavailable_raises_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable():
        raise AmgInputValidationError("cadquery_unavailable", "not installed")

    monkeypatch.setattr(input_validation, "_load_cadquery", unavailable)

    with pytest.raises(AmgInputValidationError) as exc_info:
        validate_amg_inputs(input_step=_fake_step(), amg_config=_default_config())
    assert exc_info.value.code == "cadquery_unavailable"


@pytest.mark.cad_kernel
def test_cadquery_flat_plate_step_passes_geometry_validation() -> None:
    cq = pytest.importorskip("cadquery")
    step_path = ROOT / "runs" / "pytest_tmp_local" / "test_amg_input_validation" / "cad" / "flat_plate.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    shape = cq.Workplane("XY").box(160.0, 100.0, 1.2).val()
    cq.exporters.export(shape, str(step_path))

    result = validate_amg_inputs(input_step=step_path, amg_config=_default_config())

    assert result.accepted is True
    assert result.failure_manifest is None
    checks = {check.name: check for check in result.checks}
    assert checks["single_connected_solid"].passed is True
    assert checks["constant_thickness"].measured["estimated_thickness_mm"] == pytest.approx(1.2, rel=0.05)
    assert checks["midsurface_pairing"].measured["rho_pair"] >= 0.90


@pytest.mark.cad_kernel
def test_cadquery_cube_fails_constant_thickness_validation() -> None:
    cq = pytest.importorskip("cadquery")
    step_path = ROOT / "runs" / "pytest_tmp_local" / "test_amg_input_validation" / "cad" / "cube.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    shape = cq.Workplane("XY").box(10.0, 10.0, 10.0).val()
    cq.exporters.export(shape, str(step_path))

    result = validate_amg_inputs(input_step=step_path, amg_config=_default_config())

    assert result.accepted is False
    assert result.failure_manifest is not None
    assert result.failure_manifest["reason"] == "non_constant_thickness"
    Draft202012Validator(_schema("AMG_MANIFEST_SM_V1")).validate(result.failure_manifest)
