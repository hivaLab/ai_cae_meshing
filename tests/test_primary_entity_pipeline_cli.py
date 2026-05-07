from __future__ import annotations

import json
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest
import numpy as np
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.inference.size_field_gate import build_ai_size_field_gate_report, write_ai_size_field_gate_report
from ai_mesh_generator.amg.model.size_field import build_size_field_targets
from ai_mesh_generator.amg.training._entity_common import load_entity_samples
from ai_mesh_generator.amg.inference.size_field import infer_size_field_document
from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset
from ai_mesh_generator.amg.training.size_field import train_size_field_model
from ai_mesh_generator.amg.workflow.entity_size_field_gate import run_entity_size_field_gate_workflow
from cad_dataset_factory.cdf.entity_pipeline import generate_entity_dataset, validate_entity_dataset
from cad_dataset_factory.cdf.labels.entity_labels import PartClass
from cad_dataset_factory.cdf.quality import write_size_sweep_variants
from test_brep_entity_ai_meshing_pipeline import _write_sample

ROOT = Path(__file__).resolve().parents[1]


def _tmp(name: str) -> Path:
    root = ROOT / "runs" / "pytest_tmp_local" / "primary_entity_pipeline" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fixture_dataset(name: str) -> Path:
    root = _tmp(name)
    samples = root / "samples"
    records = []
    for index, part_class in enumerate(
        [
            PartClass.SM_FLAT_PANEL,
            PartClass.SM_FLAT_PANEL,
            PartClass.SM_L_BRACKET,
            PartClass.SM_L_BRACKET,
        ],
        start=1,
    ):
        sample_id = f"sample_{index:06d}"
        _write_sample(samples, sample_id, part_class, scale=1.0 + 0.3 * index, hard_fail=index >= 3)
        records.append({"sample_id": sample_id, "path": f"samples/{sample_id}", "part_class": part_class.value})
    (root / "dataset_index.json").write_text(
        json.dumps({"schema": "CDF_ENTITY_DATASET_INDEX_SM_V2", "samples": records}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "splits").mkdir(parents=True, exist_ok=True)
    (root / "splits" / "train.txt").write_text("sample_000001\nsample_000002\nsample_000003\n", encoding="utf-8")
    (root / "splits" / "test.txt").write_text("sample_000004\n", encoding="utf-8")
    return root


def test_primary_training_and_direct_size_field_commands_write_artifacts() -> None:
    dataset = _fixture_dataset("training")
    out = _tmp("outputs")
    assert [sample.sample_id for sample in load_entity_samples(dataset, split="test")] == ["sample_000004"]
    classifier_metrics = train_part_classifier_from_dataset(dataset, out / "part_classifier", split="train", eval_split="test", seed=11, n_estimators=20, uncertainty_threshold=0.0)
    assert classifier_metrics["sample_count"] == 3
    assert classifier_metrics["evaluation"]["sample_count"] == 1
    assert (out / "part_classifier" / "model.pkl").is_file()
    assert (out / "part_classifier" / "confusion_matrix.json").is_file()
    assert (out / "part_classifier" / "eval_metrics.json").is_file()

    segmentation_metrics = train_entity_segmentation_from_dataset(dataset, out / "segmentation", split="train", eval_split="test", epochs=20, hidden_dim=16, seed=11)
    assert segmentation_metrics["sample_count"] == 3
    assert segmentation_metrics["evaluation"]["sample_count"] == 1
    assert (out / "segmentation" / "model.pt").is_file()
    assert (out / "segmentation" / "eval_metrics.json").is_file()

    size_metrics = train_size_field_model(dataset, out / "size_field_model", split="train", epochs=5, hidden_dim=16, seed=11)
    assert size_metrics["target_row_count"] >= 4
    assert size_metrics["edge_target_size_stats"]["count"] > 0
    assert "h_min_edge_fraction" in size_metrics["edge_target_size_stats"]
    assert size_metrics["learning_signal_status"] in {"SUCCESS", "FAILED_LEARNING_SIGNAL"}
    assert (out / "size_field_model" / "model.pt").is_file()
    size_field_path = out / "size_field.json"
    with pytest.raises(ValueError):
        infer_size_field_document(
            sample_dir=dataset / "samples" / "sample_000004",
            checkpoint_path=out / "size_field_model" / "model.pt",
            h0_mm=2.0,
            h_min_mm=0.5,
            h_max_mm=4.0,
            growth_rate=1.25,
        )
    document = infer_size_field_document(
        sample_dir=dataset / "samples" / "sample_000004",
        checkpoint_path=out / "size_field_model" / "model.pt",
        part_classifier_path=out / "part_classifier" / "model.pkl",
        segmentation_checkpoint_path=out / "segmentation" / "model.pt",
        h0_mm=2.0,
        h_min_mm=0.5,
        h_max_mm=4.0,
        growth_rate=1.25,
    )
    size_field_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert len(document["edge_sizes"]) > 0
    schema = json.loads((ROOT / "contracts" / "AMG_SIZE_FIELD_SM_V2.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(json.loads(size_field_path.read_text(encoding="utf-8")))


def test_ai_size_field_gate_report_uses_real_artifact_contracts() -> None:
    root = _tmp("gate_report")
    dataset = _fixture_dataset("gate_report_dataset")
    out = root / "eval"
    size_field = {
        "schema_version": "AMG_SIZE_FIELD_SM_V2",
        "sample_id": "sample_000004",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "global_mesh": {"h0_mm": 2.0, "h_min_mm": 0.5, "h_max_mm": 4.0, "growth_rate": 1.25, "quality_profile": "AMG_QA_SHELL_V2"},
        "edge_sizes": [{"edge_signature_id": "EDGE_SIG_000002_HOLE", "target_size_mm": 1.0}],
        "face_sizes": [],
    }
    predicted = root / "amg_size_field_ai.json"
    predicted.write_text(json.dumps(size_field), encoding="utf-8")
    predicted.with_name("ai_size_field_context.json").write_text(
        json.dumps(
            {
                "schema": "AMG_AI_SIZE_FIELD_CONTEXT_V1",
                "part_prediction": {"part_class": "SM_L_BRACKET", "confidence": 0.8, "probabilities": {"SM_L_BRACKET": 0.8}},
                "face_segmentation_histogram": {"BASE_PANEL": 2},
                "edge_segmentation_histogram": {"HOLE_BOUNDARY": 1},
            }
        ),
        encoding="utf-8",
    )
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "quality_evaluations" / "evaluation_000001").mkdir(parents=True, exist_ok=True)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "ansa_execution_report.json").write_text(json.dumps({"accepted": True, "sample_id": "sample_000004"}), encoding="utf-8")
    (out / "reports" / "ansa_quality_report.json").write_text(json.dumps({"accepted": True, "quality": {"num_hard_failed_elements": 0}}), encoding="utf-8")
    (out / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").write_text(
        json.dumps(
            {
                "entity_quality": [
                    {
                        "entity_signature_id": "EDGE_SIG_000002_HOLE",
                        "metric_available": True,
                        "hard_fail": False,
                        "measured_boundary_size_error": 0.1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (out / "meshes" / "ansa_size_field_mesh.bdf").write_text("$ real-shaped unit test mesh\n", encoding="utf-8")
    report = build_ai_size_field_gate_report(
        dataset_root=dataset,
        sample_dir=dataset / "samples" / "sample_000004",
        train_split="train",
        part_classifier_path=root / "part_classifier.pkl",
        segmentation_checkpoint_path=root / "segmentation.pt",
        size_field_checkpoint_path=root / "size_field.pt",
        predicted_size_field_path=predicted,
        ansa_eval_dir=out,
    )
    result = write_ai_size_field_gate_report(root / "gate_report.json", report)
    assert result.status == "SUCCESS"
    assert report["train_split_sample_count"] == 3
    assert report["edge_target_size_stats"]["count"] == 1
    assert report["edge_target_size_stats"]["std"] == 0.0
    assert report["edge_target_size_stats"]["h_min_edge_fraction"] == 0.0


def test_ai_size_field_gate_report_rejects_all_h_min_learning_signal() -> None:
    root = _tmp("gate_report_hmin")
    dataset = _fixture_dataset("gate_report_hmin_dataset")
    out = root / "eval"
    size_field = {
        "schema_version": "AMG_SIZE_FIELD_SM_V2",
        "sample_id": "sample_000004",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "global_mesh": {"h0_mm": 2.0, "h_min_mm": 0.5, "h_max_mm": 4.0, "growth_rate": 1.25, "quality_profile": "AMG_QA_SHELL_V2"},
        "edge_sizes": [{"edge_signature_id": "EDGE_SIG_000002_HOLE", "target_size_mm": 0.5}],
        "face_sizes": [],
    }
    predicted = root / "amg_size_field_ai.json"
    predicted.write_text(json.dumps(size_field), encoding="utf-8")
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "quality_evaluations" / "evaluation_000001").mkdir(parents=True, exist_ok=True)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "ansa_execution_report.json").write_text(json.dumps({"accepted": True, "sample_id": "sample_000004"}), encoding="utf-8")
    (out / "reports" / "ansa_quality_report.json").write_text(json.dumps({"accepted": True, "quality": {"num_hard_failed_elements": 0}}), encoding="utf-8")
    (out / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").write_text(
        json.dumps({"entity_quality": [{"entity_signature_id": "EDGE_SIG_000002_HOLE", "metric_available": True, "hard_fail": False, "measured_boundary_size_error": 0.0}]}),
        encoding="utf-8",
    )
    (out / "meshes" / "ansa_size_field_mesh.bdf").write_text("$ mesh\n", encoding="utf-8")
    report = build_ai_size_field_gate_report(
        dataset_root=dataset,
        sample_dir=dataset / "samples" / "sample_000004",
        train_split="train",
        part_classifier_path=root / "part_classifier.pkl",
        segmentation_checkpoint_path=root / "segmentation.pt",
        size_field_checkpoint_path=root / "size_field.pt",
        predicted_size_field_path=predicted,
        ansa_eval_dir=out,
    )
    assert report["status"] == "FAILED_LEARNING_SIGNAL"
    assert report["valid_mesh_count"] == 1
    assert report["failure_reason"] == "all_controlled_edges_at_h_min"


def test_size_sweep_variants_and_quality_aware_targets_prefer_non_hmin() -> None:
    dataset = _fixture_dataset("quality_targets")
    sample_dir = dataset / "samples" / "sample_000001"
    variants = write_size_sweep_variants(sample_dir)
    assert [variant.variant for variant in variants] == ["h_min_overrefined", "fine", "nominal", "coarse"]
    schema = json.loads((ROOT / "contracts" / "AMG_SIZE_FIELD_SM_V2.schema.json").read_text(encoding="utf-8"))
    for variant in variants:
        Draft202012Validator(schema).validate(json.loads(variant.size_field_path.read_text(encoding="utf-8")))

    better = json.loads((sample_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").read_text(encoding="utf-8"))
    better["evaluation_id"] = "evaluation_000002"
    better["entity_quality"][0]["candidate_target_size_mm"] = 1.5
    better["entity_quality"][0]["measured_boundary_size_error"] = 0.05
    better["entity_quality"][0]["measured_quality_margin"] = -0.45
    path = sample_dir / "quality_evaluations" / "evaluation_000002" / "entity_quality_labels.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(better, indent=2) + "\n", encoding="utf-8")

    sample = load_entity_samples(dataset, split="train", require_quality=True)[0]
    targets = build_size_field_targets(sample, prefer_quality_evidence=True)
    assert targets.edge_mask[1]
    assert __import__("math").exp(targets.edge_log_h[1].item()) > 0.5

    efficiency_variants = write_size_sweep_variants(sample_dir, preset="local_efficiency_v1")
    assert [variant.variant for variant in efficiency_variants] == [
        "h_min_overrefined",
        "feature_fine_far_nominal",
        "balanced",
        "far_coarse",
        "coarse_stress_test",
    ]
    for variant in efficiency_variants:
        Draft202012Validator(schema).validate(json.loads(variant.size_field_path.read_text(encoding="utf-8")))


@pytest.mark.cad_kernel
def test_cdf_entity_generate_and_validate_small_real_cad_dataset() -> None:
    pytest.importorskip("cadquery")
    dataset = _tmp("generated")
    result = generate_entity_dataset(dataset, count=1, seed=802)
    assert result.status == "SUCCESS"
    assert (dataset / "splits" / "train.txt").is_file()
    assert (dataset / "splits" / "test.txt").is_file()
    validation = validate_entity_dataset(dataset)
    assert validation.status == "SUCCESS"
    sample = dataset / "samples" / "sample_000001"
    assert (sample / "cad" / "input.step").is_file()
    assert not (sample / "labels" / "amg_manifest.json").exists()


@pytest.mark.cad_kernel
def test_diverse_quality_profile_requires_coverage_and_writes_stratified_splits() -> None:
    pytest.importorskip("cadquery")
    dataset = _tmp("generated_diverse")
    with pytest.raises(Exception) as excinfo:
        generate_entity_dataset(dataset, count=24, seed=812, profile="sm_entity_v2_diverse_quality")
    assert "invalid_profile_count" in str(excinfo.value)
    result = generate_entity_dataset(dataset, count=32, seed=812, profile="sm_entity_v2_diverse_quality")
    assert result.status == "SUCCESS"
    train_ids = [line.strip() for line in (dataset / "splits" / "train.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    test_ids = [line.strip() for line in (dataset / "splits" / "test.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(train_ids) == 24
    assert len(test_ids) == 8
    index = json.loads((dataset / "dataset_index.json").read_text(encoding="utf-8"))
    cases = {record["profile_case"] for record in index["samples"] if record["sample_id"] in test_ids}
    assert cases == {"flat_hole", "flat_slot", "flat_cutout", "flat_combo", "single_flange", "l_bracket", "u_channel", "hat_channel"}


@pytest.mark.cad_kernel
def test_learning_balanced_profile_writes_purpose_specific_splits_and_coverage() -> None:
    pytest.importorskip("cadquery")
    dataset = _tmp("generated_learning_balanced")
    with pytest.raises(Exception) as excinfo:
        generate_entity_dataset(dataset, count=56, seed=818, profile="sm_entity_v2_learning_balanced_v1")
    assert "invalid_profile_count" in str(excinfo.value)

    result = generate_entity_dataset(dataset, count=112, seed=818, profile="sm_entity_v2_learning_balanced_v1")
    assert result.status == "SUCCESS"
    for split_name in ("train", "test", "part_train", "part_test", "segmentation_train", "segmentation_test"):
        assert (dataset / "splits" / f"{split_name}.txt").is_file()

    index = json.loads((dataset / "dataset_index.json").read_text(encoding="utf-8"))
    assert index["profile"] == "sm_entity_v2_learning_balanced_v1"
    assert index["sample_count"] == 112
    assert index["profile_case_counts"]["other_block"] == 8
    assert index["profile_case_counts"]["flat_slot_long"] == 5

    coverage = json.loads((dataset / "label_coverage_report.json").read_text(encoding="utf-8"))
    required_parts = {"SM_FLAT_PANEL", "SM_SINGLE_FLANGE", "SM_L_BRACKET", "SM_U_CHANNEL", "SM_HAT_CHANNEL", "OTHER"}
    required_edges = {"OUTER_BOUNDARY", "HOLE_BOUNDARY", "SLOT_BOUNDARY", "CUTOUT_BOUNDARY", "BEND_EDGE", "FREE_EDGE", "INTERNAL"}
    for split_name in ("part_train", "part_test"):
        assert required_parts <= set(coverage["splits"][split_name]["part_class_counts"])
    for split_name in ("segmentation_train", "segmentation_test"):
        assert required_edges <= set(coverage["splits"][split_name]["edge_semantic_counts"])

    sample = dataset / "samples" / "sample_000001"
    with np.load(sample / "graph" / "brep_graph.npz", allow_pickle=False) as arrays:
        assert all("target" not in key.lower() and "label" not in key.lower() and "quality" not in key.lower() for key in arrays.files)


def test_entity_size_field_workflow_uses_file_contract_for_ansa(monkeypatch) -> None:
    dataset = _fixture_dataset("workflow_dataset")
    out = _tmp("workflow_out")
    calls: list[list[str]] = []

    def fake_run(command, capture_output, text, timeout, check):  # noqa: ANN001
        calls.append(list(command))
        out_dir = Path(command[command.index("--out") + 1])
        size_field_path = Path(command[command.index("--size-field") + 1])
        size_field = json.loads(size_field_path.read_text(encoding="utf-8"))
        first_edge = size_field["edge_sizes"][0]
        out_dir.joinpath("reports").mkdir(parents=True, exist_ok=True)
        out_dir.joinpath("quality_evaluations", "evaluation_000001").mkdir(parents=True, exist_ok=True)
        out_dir.joinpath("meshes").mkdir(parents=True, exist_ok=True)
        out_dir.joinpath("reports", "ansa_execution_report.json").write_text(json.dumps({"accepted": True, "sample_id": "sample_000004"}), encoding="utf-8")
        out_dir.joinpath("reports", "ansa_quality_report.json").write_text(
            json.dumps({"accepted": True, "mesh_stats": {"shell_element_count": 12}, "quality": {"num_hard_failed_elements": 0}}),
            encoding="utf-8",
        )
        out_dir.joinpath("quality_evaluations", "evaluation_000001", "entity_quality_labels.json").write_text(
            json.dumps(
                {
                    "entity_quality": [
                        {
                            "entity_signature_id": first_edge["edge_signature_id"],
                            "metric_available": True,
                            "hard_fail": False,
                            "measured_boundary_size_error": 0.1,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out_dir.joinpath("meshes", "ansa_size_field_mesh.bdf").write_text("$ workflow unit-test bdf\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout='{"status":"COMPLETED"}', stderr="")

    monkeypatch.setattr("ai_mesh_generator.amg.workflow.entity_size_field_gate.subprocess.run", fake_run)
    report = run_entity_size_field_gate_workflow(
        dataset=dataset,
        ansa_executable=str(ROOT / "fake_ansa64.bat"),
        out=out,
        train_split="train",
        test_split="test",
        epochs_segmentation=2,
        epochs_size_field=2,
        seed=31,
        timeout_sec=30,
    )
    assert calls
    assert calls[0][2:5] == ["cad_dataset_factory.cdf.entity_cli", "ansa-evaluate-size-field", "--sample-dir"]
    assert (out / "workflow_report.json").is_file()
    assert report["gate"]["attempted_count"] == 1
    assert report["gate"]["valid_mesh_count"] == 1
