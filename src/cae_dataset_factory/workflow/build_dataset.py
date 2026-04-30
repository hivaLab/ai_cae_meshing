from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from cae_mesh_common.schema.validators import load_json_or_yaml, validate_all_repository_schemas
from cae_dataset_factory.config.generation_spec import GenerationSpec, load_generation_spec
from cae_dataset_factory.dataset.dataset_indexer import write_dataset_index
from cae_dataset_factory.dataset.split_builder import write_splits
from cae_dataset_factory.workflow.generate_sample import generate_sample
from cae_dataset_factory.workflow.mesh_sample import mesh_and_write_sample


def build_dataset(
    spec_path: Path | str,
    output_dir: Path | str,
    num_samples: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    spec = load_generation_spec(spec_path)
    output_dir = Path(output_dir)
    if force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_all_repository_schemas()
    mesh_profile = load_json_or_yaml(Path("configs/amg/default_mesh_profile.yaml"))
    target = num_samples or spec.accepted_target
    rows: list[dict[str, Any]] = []
    attempts = 0
    while len(rows) < target:
        assembly = generate_sample(attempts, spec.seed, spec.defect_rate)
        row = mesh_and_write_sample(assembly, output_dir, mesh_profile)
        attempts += 1
        if row["accepted"]:
            rows.append(row)
    sample_ids = [row["sample_id"] for row in rows]
    train = min(spec.train_count, len(sample_ids))
    val = min(spec.val_count, max(0, len(sample_ids) - train))
    test = min(spec.test_count, max(0, len(sample_ids) - train - val))
    if num_samples is not None and num_samples != spec.accepted_target:
        train = int(num_samples * 0.8)
        val = int(num_samples * 0.1)
        test = num_samples - train - val
    write_dataset_index(rows, output_dir)
    splits = write_splits(sample_ids, output_dir, train, val, test)
    manifest = {
        "dataset_id": spec.dataset_id,
        "schema_version": "0.1.0",
        "seed": spec.seed,
        "accepted_count": len(rows),
        "rejected_count": attempts - len(rows),
        "splits": {name: len(ids) for name, ids in splits.items()},
        "backend": spec.backend,
        "acceptance_rate": len(rows) / attempts,
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"manifest": manifest, "rows": rows}
