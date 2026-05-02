from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cae_mesh_common.bdf.bdf_validator import validate_bdf
from cae_mesh_common.cad.step_io import inspect_step_brep, validate_feature_bearing_step
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
    topology_family_count: int = 0
    graph_node_shape_unique_count: int = 0
    mesh_size_label_coverage: float = 0.0
    rejected_ratio: float = 0.0

    @property
    def passed(self) -> bool:
        diversity_ok = True
        if self.accepted_count >= 50:
            diversity_ok = (
                self.topology_family_count >= 5
                and self.graph_node_shape_unique_count >= 20
                and self.mesh_size_label_coverage >= 0.95
                and self.rejected_ratio >= 0.10
            )
        return (
            self.accepted_count > 0
            and self.bdf_failures == 0
            and self.schema_failures == 0
            and self.missing_artifacts == 0
            and self.step_brep_failures == 0
            and self.split_mismatch_count == 0
            and diversity_ok
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
            "topology_family_count": self.topology_family_count,
            "graph_node_shape_unique_count": self.graph_node_shape_unique_count,
            "mesh_size_label_coverage": self.mesh_size_label_coverage,
            "rejected_ratio": self.rejected_ratio,
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
    topology_families: set[str] = set()
    graph_node_shapes: set[tuple[int, int, int, int, int, int]] = set()
    mesh_size_labeled = 0
    mesh_size_expected = 0
    for _, row in index.iterrows():
        for column in ["input_zip", "bdf_path", "graph_path", "label_path", "label_json_path", "recipe_path", "qa_metrics_path"]:
            if not Path(row[column]).exists():
                missing += 1
        sample_dir = Path(row["sample_dir"])
        topology_families.add(str(row.get("topology_family", "unknown")))
        required_sample_artifacts = [
            sample_dir / "input_package/geometry/assembly.step",
            sample_dir / "input_package/metadata/manifest.json",
            sample_dir / "input_package/metadata/product_tree.json",
            sample_dir / "input_package/metadata/part_attributes.csv",
            sample_dir / "input_package/metadata/material_library.json",
            sample_dir / "input_package/metadata/connections.csv",
            sample_dir / "input_package/metadata/boundary_named_sets.json",
            sample_dir / "input_package/metadata/geometry_feature_evidence.json",
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
            assembly_path = sample_dir / "input_package/metadata/assembly.json"
            if assembly_path.exists():
                assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
                step_info = validate_feature_bearing_step(step_path, assembly.get("parts", []))
                if not step_info["feature_bearing"]:
                    step_brep_failures += 1
            else:
                step_info = inspect_step_brep(step_path)
                if not step_info["valid_step"] or not step_info["is_ap242"] or not step_info["is_brep"] or step_info["descriptor_only"]:
                    step_brep_failures += 1
        else:
            step_brep_failures += 1
        if Path(row["graph_path"]).exists():
            graph = load_graph(row["graph_path"])
            graph_node_shapes.add(
                (
                    len(graph.node_sets.get("part", [])),
                    len(graph.node_sets.get("face", [])),
                    len(graph.node_sets.get("edge", [])),
                    len(graph.node_sets.get("contact_candidate", [])),
                    len(graph.node_sets.get("connection", [])),
                    sum(len(edges) for edges in graph.edge_sets.values()),
                )
            )
            mesh_size_expected += (
                len(graph.node_sets.get("part", []))
                + len(graph.node_sets.get("face", []))
                + len(graph.node_sets.get("edge", []))
                + len(graph.node_sets.get("contact_candidate", []))
            )
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
        label_path = Path(row["label_json_path"])
        if label_path.exists():
            try:
                labels = json.loads(label_path.read_text(encoding="utf-8"))
                size_records = labels.get("mesh_size_labels", [])
                mesh_size_labeled += sum(
                    1
                    for item in size_records
                    if item.get("target_type") in {"part", "face", "edge", "contact_candidate"}
                )
            except Exception:
                schema_failures += 1
        result = validate_bdf(row["bdf_path"])
        if bool(row.get("accepted", False)) and not result.passed:
            bdf_failures += 1
    train_ids = read_split(dataset_dir, "train") if (dataset_dir / "splits/train.txt").exists() else []
    val_ids = read_split(dataset_dir, "val") if (dataset_dir / "splits/val.txt").exists() else []
    test_ids = read_split(dataset_dir, "test") if (dataset_dir / "splits/test.txt").exists() else []
    split_ids = train_ids + val_ids + test_ids
    split_mismatch_count = 0
    if len(split_ids) != len(set(split_ids)):
        split_mismatch_count += 1
    accepted_ids = set(index[index["accepted"]]["sample_id"])
    if set(split_ids) != accepted_ids:
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
        topology_family_count=len(topology_families),
        graph_node_shape_unique_count=len(graph_node_shapes),
        mesh_size_label_coverage=round(mesh_size_labeled / mesh_size_expected, 6) if mesh_size_expected else 0.0,
        rejected_ratio=round((len(index) - int(index["accepted"].sum())) / max(len(index), 1), 6),
    )
    (dataset_dir / "dataset_validation.json").write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return summary
