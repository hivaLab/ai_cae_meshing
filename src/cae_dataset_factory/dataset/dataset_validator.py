from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cae_mesh_common.bdf.bdf_validator import validate_bdf
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
    missing_artifacts: int

    @property
    def passed(self) -> bool:
        return self.accepted_count > 0 and self.bdf_failures == 0 and self.missing_artifacts == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_dir": str(self.dataset_dir),
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "train_count": self.train_count,
            "val_count": self.val_count,
            "test_count": self.test_count,
            "bdf_failures": self.bdf_failures,
            "missing_artifacts": self.missing_artifacts,
            "passed": self.passed,
        }


def validate_dataset(dataset_dir: Path | str) -> DatasetValidationSummary:
    dataset_dir = Path(dataset_dir)
    manifest = validate_json_file(dataset_dir / "dataset_manifest.json", "dataset_manifest.schema.json")
    index = read_dataset_index(dataset_dir)
    missing = 0
    bdf_failures = 0
    for _, row in index.iterrows():
        for column in ["input_zip", "bdf_path", "graph_path", "label_path"]:
            if not Path(row[column]).exists():
                missing += 1
        if Path(row["graph_path"]).exists():
            load_graph(row["graph_path"])
        result = validate_bdf(row["bdf_path"])
        if not result.passed:
            bdf_failures += 1
    summary = DatasetValidationSummary(
        dataset_dir=dataset_dir,
        accepted_count=int(index["accepted"].sum()),
        rejected_count=int(manifest.get("rejected_count", 0)),
        train_count=len(read_split(dataset_dir, "train")) if (dataset_dir / "splits/train.txt").exists() else 0,
        val_count=len(read_split(dataset_dir, "val")) if (dataset_dir / "splits/val.txt").exists() else 0,
        test_count=len(read_split(dataset_dir, "test")) if (dataset_dir / "splits/test.txt").exists() else 0,
        bdf_failures=bdf_failures,
        missing_artifacts=missing,
    )
    (dataset_dir / "dataset_validation.json").write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return summary
