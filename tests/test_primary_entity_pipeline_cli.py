from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.optimization.size_field import optimize_size_field_for_sample
from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.quality_surrogate import train_quality_surrogate_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset
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
    return root


def test_primary_training_and_optimization_commands_write_artifacts() -> None:
    dataset = _fixture_dataset("training")
    out = _tmp("outputs")
    classifier_metrics = train_part_classifier_from_dataset(dataset, out / "part_classifier", seed=11, n_estimators=20, uncertainty_threshold=0.0)
    assert classifier_metrics["sample_count"] == 4
    assert (out / "part_classifier" / "model.pkl").is_file()
    assert (out / "part_classifier" / "confusion_matrix.json").is_file()

    segmentation_metrics = train_entity_segmentation_from_dataset(dataset, out / "segmentation", epochs=1, hidden_dim=16, seed=11)
    assert segmentation_metrics["sample_count"] == 4
    assert (out / "segmentation" / "model.pt").is_file()

    surrogate_metrics = train_quality_surrogate_from_dataset(dataset, out / "quality_surrogate", seed=11)
    assert surrogate_metrics["row_count"] >= 4
    size_field_path = out / "size_field.json"
    report = optimize_size_field_for_sample(
        dataset / "samples" / "sample_000001",
        out / "quality_surrogate" / "model.pkl",
        size_field_path,
        h0_mm=2.0,
        h_min_mm=0.5,
        h_max_mm=4.0,
        growth_rate=1.25,
    )
    assert report["selected_entity_count"] > 0
    schema = json.loads((ROOT / "contracts" / "AMG_SIZE_FIELD_SM_V2.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(json.loads(size_field_path.read_text(encoding="utf-8")))


@pytest.mark.cad_kernel
def test_cdf_entity_generate_and_validate_small_real_cad_dataset() -> None:
    pytest.importorskip("cadquery")
    dataset = _tmp("generated")
    result = generate_entity_dataset(dataset, count=1, seed=802)
    assert result.status == "SUCCESS"
    validation = validate_entity_dataset(dataset)
    assert validation.status == "SUCCESS"
    sample = dataset / "samples" / "sample_000001"
    assert (sample / "cad" / "input.step").is_file()
    assert not (sample / "labels" / "amg_manifest.json").exists()
