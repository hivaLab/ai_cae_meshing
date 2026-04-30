from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cae_mesh_common.bdf.bdf_validator import validate_bdf
from cae_mesh_common.cad.step_io import inspect_step_brep
from cae_mesh_common.graph.hetero_graph import load_graph
from cae_mesh_common.schema.validators import validate_json_file
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index
from cae_dataset_factory.dataset.split_builder import read_split


@dataclass
class DatasetValidationSummary:
    dataset_dir: Path
    accepted_count: int
    rejected_count: int
    train_count: int
    val_count: int
    test_count: int
    bdf_failures: int
    schema_failures: int
    missing_artifacts: int
    step_brep_failures: int
    split_mismatch_count: int

    @property
    def passed(self) -> bool:
        return (
            self.accepted_count > 0
            and self.bdf_failures == 0
            and self.schema_failures == 0
            and self.missing_artifacts == 0
            and self.step_brep_failures == 0
            and self.split_mismatch_count == 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_dir": str(self.dataset_dir),
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "train_count": self.train_count,
            "val_count": self.val_count,
            "test_count": self.test_count,
            "bdf_failures": self.bdf_failures,
            "schema_failures": self.schema_failures,
            "missing_artifacts": self.missing_artifacts,
            "step_brep_failures": self.step_brep_failures,
            "split_mismatch_count": self.split_mismatch_count,
            "passed": self.passed,
        }


def validate_dataset(dataset_dir: Path | str) -> DatasetValidationSummary:
    dataset_dir = Path(dataset_dir)
    manifest = validate_json_file(dataset_dir / "dataset_manifest.json", "dataset_manifest.schema.json")
    index = read_dataset_index(dataset_dir)
    missing = 0
    bdf_failures = 0
    schema_failures = 0
    step_brep_failures = 0
    for _, row in index.iterrows():
        for column in ["input_zip", "bdf_path", "graph_path", "label_path", "label_json_path", "recipe_path", "qa_metrics_path"]:
            if not Path(row[column]).exists():
                missing += 1
        sample_dir = Path(row["sample_dir"])
        required_sample_artifacts = [
            sample_dir / "input_package/geometry/assembly.step",
            sample_dir / "input_package/metadata/manifest.json",
            sample_dir / "input_package/metadata/product_tree.json",
            sample_dir / "input_package/metadata/part_attributes.csv",
            sample_dir / "input_package/metadata/material_library.json",
            sample_dir / "input_package/metadata/connections.csv",
            sample_dir / "input_package/metadata/boundary_named_sets.json",
            sample_dir / "graphs/graph.pt",
            sample_dir / "graphs/brep_graph.json",
            sample_dir / "graphs/assembly_graph.json",
            sample_dir / "mesh/solver_deck/model_final.bdf",
            sample_dir / "mesh/report/qa_metrics_global.json",
            sample_dir / "mesh/report/qa_metrics_part.csv",
            sample_dir / "mesh/report/qa_metrics_element.parquet",
            sample_dir / "mesh/viewer/mesh_preview.vtk",
        ]
        missing += sum(1 for path in required_sample_artifacts if not path.exists())
        step_path = sample_dir / "input_package/geometry/assembly.step"
        if step_path.exists():
            step_info = inspect_step_brep(step_path)
            if not step_info["valid_step"] or not step_info["is_ap242"] or not step_info["is_brep"] or step_info["descriptor_only"]:
                step_brep_failures += 1
        if Path(row["graph_path"]).exists():
            load_graph(row["graph_path"])
        for path, schema in [
            (sample_dir / "input_package/metadata/manifest.json", "input_package.schema.json"),
            (sample_dir / "input_package/metadata/product_tree.json", "product_tree.schema.json"),
            (sample_dir / "input_package/metadata/material_library.json", "material_library.schema.json"),
            (Path(row["label_json_path"]), "label.schema.json"),
            (Path(row["recipe_path"]), "mesh_recipe.schema.json"),
            (Path(row["qa_metrics_path"]), "qa_metric.schema.json"),
        ]:
            if path.exists():
                try:
                    validate_json_file(path, schema)
                except Exception:
                    schema_failures += 1
        result = validate_bdf(row["bdf_path"])
        if not result.passed:
            bdf_failures += 1
    train_ids = read_split(dataset_dir, "train") if (dataset_dir / "splits/train.txt").exists() else []
    val_ids = read_split(dataset_dir, "val") if (dataset_dir / "splits/val.txt").exists() else []
    test_ids = read_split(dataset_dir, "test") if (dataset_dir / "splits/test.txt").exists() else []
    split_ids = train_ids + val_ids + test_ids
    split_mismatch_count = 0
    if len(split_ids) != len(set(split_ids)):
        split_mismatch_count += 1
    if set(split_ids) != set(index["sample_id"]):
        split_mismatch_count += 1
    expected_splits = manifest.get("splits", {})
    if expected_splits:
        if len(train_ids) != int(expected_splits.get("train", -1)):
            split_mismatch_count += 1
        if len(val_ids) != int(expected_splits.get("val", -1)):
            split_mismatch_count += 1
        if len(test_ids) != int(expected_splits.get("test", -1)):
            split_mismatch_count += 1
    summary = DatasetValidationSummary(
        dataset_dir=dataset_dir,
        accepted_count=int(index["accepted"].sum()),
        rejected_count=int(manifest.get("rejected_count", 0)),
        train_count=len(train_ids),
        val_count=len(val_ids),
        test_count=len(test_ids),
        bdf_failures=bdf_failures,
        schema_failures=schema_failures,
        missing_artifacts=missing,
        step_brep_failures=step_brep_failures,
        split_mismatch_count=split_mismatch_count,
    )
    (dataset_dir / "dataset_validation.json").write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return summary
