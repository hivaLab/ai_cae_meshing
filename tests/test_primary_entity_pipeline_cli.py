from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.inference.size_field_gate import build_ai_size_field_gate_report, write_ai_size_field_gate_report
from ai_mesh_generator.amg.training._entity_common import load_entity_samples
from ai_mesh_generator.amg.inference.size_field import infer_size_field_document
from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset
from ai_mesh_generator.amg.training.size_field import train_size_field_model
from cad_dataset_factory.cdf.entity_pipeline import generate_entity_dataset, validate_entity_dataset
from cad_dataset_factory.cdf.labels.entity_labels import PartClass
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
    classifier_metrics = train_part_classifier_from_dataset(dataset, out / "part_classifier", split="train", seed=11, n_estimators=20, uncertainty_threshold=0.0)
    assert classifier_metrics["sample_count"] == 3
    assert (out / "part_classifier" / "model.pkl").is_file()
    assert (out / "part_classifier" / "confusion_matrix.json").is_file()

    segmentation_metrics = train_entity_segmentation_from_dataset(dataset, out / "segmentation", split="train", epochs=20, hidden_dim=16, seed=11)
    assert segmentation_metrics["sample_count"] == 3
    assert (out / "segmentation" / "model.pt").is_file()

    size_metrics = train_size_field_model(dataset, out / "size_field_model", split="train", epochs=5, hidden_dim=16, seed=11)
    assert size_metrics["target_row_count"] >= 4
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
