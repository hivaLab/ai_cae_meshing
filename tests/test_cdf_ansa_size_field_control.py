from __future__ import annotations

import json
import shutil
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.entity_pipeline import validate_entity_dataset
from cad_dataset_factory.cdf.labels.entity_labels import validate_entity_label_document
from cad_dataset_factory.cdf.oracle.ansa_size_field import (
    AnsaSizeFieldEvaluationRequest,
    build_ansa_size_field_command,
    build_size_field_payload,
    run_ansa_size_field_evaluation,
)
from cad_dataset_factory.cdf.oracle.ansa_entity_probe import (
    AnsaEntityProbeRequest,
    build_ansa_entity_probe_command,
    build_ansa_entity_probe_payload,
)
from cad_dataset_factory.cdf.oracle.ansa_scripts.cdf_ansa_size_field import (
    EntityDescriptor,
    SizeFieldScriptError,
    match_descriptors,
    measure_bdf_entity_length_stats,
    run_size_field_workflow,
)
from test_brep_entity_ai_meshing_pipeline import _write_sample
from cad_dataset_factory.cdf.labels.entity_labels import PartClass

ROOT = Path(__file__).resolve().parents[1]


def _tmp(name: str) -> Path:
    root = ROOT / "runs" / "pytest_tmp_local" / "cdf_ansa_size_field" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _sample(root: Path) -> Path:
    sample_dir = _write_sample(root / "samples", "sample_000001", PartClass.SM_FLAT_PANEL)
    (sample_dir / "cad").mkdir(parents=True, exist_ok=True)
    (sample_dir / "cad" / "input.step").write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
    cdf_size_field = json.loads((sample_dir / "labels" / "mesh_size_field.json").read_text(encoding="utf-8"))
    cdf_size_field["schema_version"] = "AMG_SIZE_FIELD_SM_V2"
    (sample_dir / "amg_size_field.json").write_text(json.dumps(cdf_size_field, indent=2) + "\n", encoding="utf-8")
    (root / "dataset_index.json").write_text(
        json.dumps({"schema": "CDF_ENTITY_DATASET_INDEX_SM_V2", "samples": [{"sample_id": "sample_000001", "path": "samples/sample_000001"}]})
        + "\n",
        encoding="utf-8",
    )
    return sample_dir


def _request(sample_dir: Path, out_dir: Path) -> AnsaSizeFieldEvaluationRequest:
    return AnsaSizeFieldEvaluationRequest(
        sample_dir=sample_dir,
        size_field_path=Path("amg_size_field.json"),
        ansa_executable=str(ROOT / "fake_ansa64.bat"),
        out_dir=out_dir,
        timeout_sec=30,
    )


class FakeSizeFieldAdapter:
    def __init__(self, *, match: bool = True, local_metric: bool = True) -> None:
        self.match = match
        self.local_metric = local_metric
        self.calls: list[str] = []

    def ansa_version(self) -> str:
        return "fake-ansa-for-unit-test"

    def import_step(self, cad_path: str) -> bool:
        self.calls.append("import_step")
        return Path(cad_path).is_file()

    def cleanup_geometry(self) -> bool:
        self.calls.append("cleanup_geometry")
        return True

    def extract_midsurface(self) -> bool:
        self.calls.append("extract_midsurface")
        return True

    def collect_edge_descriptors(self) -> list[dict[str, Any]]:
        if not self.match:
            return []
        return [{"signature_id": "EDGE_SIG_000002_HOLE", "entity": {"kind": "edge"}, "index": 0, "length": 2.0}]

    def collect_face_descriptors(self) -> list[dict[str, Any]]:
        return []

    def apply_global_mesh(self, h0_mm: float, h_min_mm: float, h_max_mm: float, growth_rate: float) -> None:
        self.calls.append(f"global:{h0_mm}:{growth_rate}")

    def apply_edge_size(self, entity: Any, target_size_mm: float) -> None:
        self.calls.append(f"edge:{target_size_mm}")

    def apply_face_size(self, entity: Any, target_size_mm: float) -> None:
        self.calls.append(f"face:{target_size_mm}")

    def run_batch_mesh(self, session_name: str, timeout_sec: int) -> bool:
        self.calls.append("batch_mesh")
        return True

    def export_solver_deck(self, mesh_path: str, solver_deck: str) -> bool:
        self.calls.append("export")
        Path(mesh_path).parent.mkdir(parents=True, exist_ok=True)
        Path(mesh_path).write_text("$ real unit-test bdf\nCQUAD4,1,1,1,2,3,4\n", encoding="utf-8")
        return True

    def global_quality(self) -> dict[str, Any]:
        return {"num_hard_failed_elements": 0, "mesh_stats": {"shell_element_count": 1}}

    def measure_entity_length_stats(self, entity: Any) -> dict[str, float] | None:
        if not self.local_metric:
            return None
        return {"average": 1.0, "min": 1.0, "max": 1.0}


def test_size_field_command_payload_contains_entity_contract_paths() -> None:
    sample_dir = _sample(_tmp("payload_dataset"))
    request = _request(sample_dir, _tmp("payload_out"))
    payload = build_size_field_payload(request)
    assert payload["size_field"].endswith("amg_size_field.json")
    assert payload["entity_signatures"].endswith("graph/entity_signatures.json")
    assert payload["graph_npz"].endswith("graph/brep_graph.npz")
    assert payload["mesh_path"].endswith("meshes/ansa_size_field_mesh.bdf")
    command = build_ansa_size_field_command(request)
    assert any("cdf_ansa_size_field.py" in item for item in command)
    assert any(item.startswith("-process_string:") for item in command)


def test_size_field_payload_accepts_repo_relative_size_field_paths() -> None:
    sample_dir = _sample(_tmp("repo_relative_dataset"))
    root_relative = sample_dir.relative_to(ROOT) / "amg_size_field.json"
    request = AnsaSizeFieldEvaluationRequest(
        sample_dir=sample_dir,
        size_field_path=root_relative,
        ansa_executable=str(ROOT / "fake_ansa64.bat"),
        out_dir=_tmp("repo_relative_out"),
    )
    payload = build_size_field_payload(request)
    assert payload["size_field"].endswith("samples/sample_000001/amg_size_field.json")


def test_entity_probe_command_payload_contains_cad_and_signature_paths() -> None:
    sample_dir = _sample(_tmp("probe_dataset"))
    fake_executable = ROOT / "runs" / "pytest_tmp_local" / "cdf_ansa_size_field" / "fake_probe_ansa64.bat"
    fake_executable.parent.mkdir(parents=True, exist_ok=True)
    fake_executable.write_text("@echo off\n", encoding="utf-8")
    request = AnsaEntityProbeRequest(
        sample_dir=sample_dir,
        ansa_executable=str(fake_executable),
        out=_tmp("probe_out") / "ansa_entity_probe.json",
    )
    payload = build_ansa_entity_probe_payload(request)
    assert payload["cad_path"].endswith("cad/input.step")
    assert payload["entity_signatures"].endswith("graph/entity_signatures.json")
    command = build_ansa_entity_probe_command(request)
    assert any("cdf_ansa_entity_probe.py" in item for item in command)
    assert any(item.startswith("-process_string:") for item in command)


def test_descriptor_matching_requires_real_geometry_descriptor() -> None:
    cdf = [EntityDescriptor(signature_id="EDGE_A", index=0, entity_type="EDGE", entity=None, length=2.0)]
    ansa = [EntityDescriptor(signature_id="EDGE_A", index=0, entity_type="EDGE", entity=object())]
    with pytest.raises(SizeFieldScriptError) as excinfo:
        match_descriptors(cdf, ansa)
    assert excinfo.value.code == "entity_matching_failed"


def test_slot_arc_matching_uses_endpoints_when_arc_centers_disagree() -> None:
    cdf = [
        EntityDescriptor(
            signature_id="EDGE_SLOT_ARC",
            index=0,
            entity_type="EDGE",
            entity=None,
            curve_type_id=2,
            length=10.995574,
            bbox=(3.5, 7.0, 0.0),
            center=(99.128169, 60.5, 0.75),
            anchor=(96.9, 64.0, 0.75),
            endpoint=(96.9, 57.0, 0.75),
        )
    ]
    ansa_entity = object()
    ansa = [
        EntityDescriptor(
            signature_id=None,
            index=0,
            entity_type="EDGE",
            entity=ansa_entity,
            curve_type_id=2,
            length=10.984273,
            bbox=(0.0, 7.0, 0.0),
            center=(96.9, 60.5, 0.75),
            anchor=(96.9, 57.0, 0.75),
            endpoint=(96.9, 64.0, 0.75),
        )
    ]
    matches = match_descriptors(cdf, ansa)
    assert matches["EDGE_SLOT_ARC"].entity is ansa_entity


def test_duplicate_slot_arc_descriptors_remain_ambiguous() -> None:
    cdf = [
        EntityDescriptor(
            signature_id="EDGE_SLOT_ARC",
            index=0,
            entity_type="EDGE",
            entity=None,
            curve_type_id=2,
            length=10.995574,
            bbox=(3.5, 7.0, 0.0),
            anchor=(96.9, 64.0, 0.75),
            endpoint=(96.9, 57.0, 0.75),
        )
    ]
    ansa = [
        EntityDescriptor(index=0, signature_id=None, entity_type="EDGE", entity=object(), curve_type_id=2, length=10.995574, bbox=(0.0, 7.0, 0.0), anchor=(96.9, 57.0, 0.75), endpoint=(96.9, 64.0, 0.75)),
        EntityDescriptor(index=1, signature_id=None, entity_type="EDGE", entity=object(), curve_type_id=2, length=10.995574, bbox=(0.0, 7.0, 0.0), anchor=(96.9, 57.0, 0.75), endpoint=(96.9, 64.0, 0.75)),
    ]
    with pytest.raises(SizeFieldScriptError) as excinfo:
        match_descriptors(cdf, ansa)
    assert excinfo.value.code == "entity_matching_failed"
    assert excinfo.value.diagnostics["ambiguous"][0]["signature_id"] == "EDGE_SLOT_ARC"


def test_bdf_entity_length_stats_measure_real_mesh_segments() -> None:
    root = _tmp("bdf_metric")
    bdf = root / "mesh.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID           1              0.      0.      0.",
                "GRID           2              1.      0.      0.",
                "GRID           3              2.      0.      0.",
                "GRID           4              0.      1.      0.",
                "GRID           5              1.      1.      0.",
                "GRID           6              2.      1.      0.",
                "CQUAD4         1       1       1       2       5       4",
                "CQUAD4         2       1       2       3       6       5",
                "ENDDATA",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    descriptor = EntityDescriptor(
        signature_id="EDGE_LINE",
        index=0,
        entity_type="EDGE",
        entity=None,
        curve_type_id=1,
        length=2.0,
        center=(1.0, 0.0, 0.0),
        anchor=(0.0, 0.0, 0.0),
    )
    stats = measure_bdf_entity_length_stats(bdf, descriptor, 1.0)
    assert stats is not None
    assert stats["count"] == 2.0
    assert stats["average"] == pytest.approx(1.0)


def test_size_field_workflow_with_fake_adapter_writes_real_shaped_outputs() -> None:
    sample_dir = _sample(_tmp("success_dataset"))
    out_dir = _tmp("success_out")
    payload = build_size_field_payload(_request(sample_dir, out_dir))
    adapter = FakeSizeFieldAdapter()
    assert run_size_field_workflow(payload, adapter) == 0
    execution = json.loads((out_dir / "reports" / "ansa_execution_report.json").read_text(encoding="utf-8"))
    quality = json.loads((out_dir / "reports" / "ansa_quality_report.json").read_text(encoding="utf-8"))
    entity_quality = json.loads((out_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").read_text(encoding="utf-8"))
    Draft202012Validator(_schema("CDF_ANSA_EXECUTION_REPORT_SM_V1")).validate(execution)
    Draft202012Validator(_schema("CDF_ANSA_QUALITY_REPORT_SM_V1")).validate(quality)
    validate_entity_label_document(entity_quality)
    assert execution["accepted"] is True
    assert quality["quality"]["num_hard_failed_elements"] == 0
    assert entity_quality["entity_quality"][0]["metric_available"] is True
    assert "edge:1.0" in adapter.calls
    assert (out_dir / "meshes" / "ansa_size_field_mesh.bdf").stat().st_size > 0


def test_size_field_workflow_blocks_unmatched_entities() -> None:
    sample_dir = _sample(_tmp("blocked_dataset"))
    out_dir = _tmp("blocked_out")
    payload = build_size_field_payload(_request(sample_dir, out_dir))
    assert run_size_field_workflow(payload, FakeSizeFieldAdapter(match=False)) == 2
    diagnostics = json.loads((out_dir / "reports" / "ansa_size_field_diagnostics.json").read_text(encoding="utf-8"))
    entity_quality = json.loads((out_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").read_text(encoding="utf-8"))
    assert diagnostics["status"] == "BLOCKED"
    assert diagnostics["error_code"] == "entity_matching_failed"
    assert entity_quality["entity_quality"][0]["metric_available"] is False


def test_entity_validation_requires_available_local_quality_metrics() -> None:
    root = _tmp("validate_unavailable")
    sample_dir = _sample(root)
    quality_path = sample_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["entity_quality"][0].pop("measured_boundary_size_error", None)
    quality["entity_quality"][0]["metric_available"] = False
    quality["entity_quality"][0]["metric_unavailable_reason"] = "entity_length_statistics_unavailable"
    quality_path.write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    result = validate_entity_dataset(root, require_quality=True)
    assert result.status == "VALIDATION_FAILED"
    assert any("entity_quality_metric_unavailable" in error for error in result.errors)


def test_runner_does_not_treat_zero_process_return_as_success_when_reports_reject(monkeypatch) -> None:
    sample_dir = _sample(_tmp("postvalidate_dataset"))
    out_dir = _tmp("postvalidate_out")
    fake_executable = ROOT / "runs" / "pytest_tmp_local" / "cdf_ansa_size_field" / "fake_ansa64.bat"
    fake_executable.parent.mkdir(parents=True, exist_ok=True)
    fake_executable.write_text("@echo off\n", encoding="utf-8")
    request = AnsaSizeFieldEvaluationRequest(
        sample_dir=sample_dir,
        size_field_path=Path("amg_size_field.json"),
        ansa_executable=str(fake_executable),
        out_dir=out_dir,
    )

    def fake_run(command, capture_output, text, timeout, check, **_kwargs):  # noqa: ANN001
        payload = build_size_field_payload(request)
        Path(payload["diagnostics"]).parent.mkdir(parents=True, exist_ok=True)
        Path(payload["diagnostics"]).write_text(json.dumps({"status": "BLOCKED", "error_code": "entity_matching_failed"}), encoding="utf-8")
        Path(payload["execution_report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(payload["execution_report"]).write_text(
            json.dumps(
                {
                    "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
                    "sample_id": "sample_000001",
                    "accepted": False,
                    "step_import_success": True,
                    "midsurface_extraction_success": True,
                    "feature_matching_success": False,
                    "batch_mesh_success": False,
                    "solver_export_success": False,
                }
            ),
            encoding="utf-8",
        )
        Path(payload["quality_report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(payload["quality_report"]).write_text(
            json.dumps(
                {
                    "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
                    "sample_id": "sample_000001",
                    "accepted": False,
                    "mesh_stats": {},
                    "quality": {"num_hard_failed_elements": 0, "entity_local_metrics_available": False},
                }
            ),
            encoding="utf-8",
        )
        Path(payload["entity_quality"]).parent.mkdir(parents=True, exist_ok=True)
        Path(payload["entity_quality"]).write_text(
            json.dumps(
                {
                    "schema_version": "CDF_ENTITY_QUALITY_EVALUATION_SM_V2",
                    "sample_id": "sample_000001",
                    "evaluation_id": "evaluation_000001",
                    "size_field_path": "amg_size_field.json",
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
                            "metric_unavailable_reason": "entity_matching_failed",
                        }
                    ],
                    "global_quality_summary": {"accepted": False},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("cad_dataset_factory.cdf.oracle.ansa_size_field.subprocess.run", fake_run)
    result = run_ansa_size_field_evaluation(request)
    assert result.status == "BLOCKED"
    assert result.returncode == 0
    assert result.error_code == "entity_matching_failed"
