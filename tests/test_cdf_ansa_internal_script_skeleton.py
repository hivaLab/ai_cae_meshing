from __future__ import annotations

import json
from pathlib import Path

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
