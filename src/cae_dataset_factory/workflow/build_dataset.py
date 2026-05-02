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
    accepted_rows: list[dict[str, Any]] = []
    rejections: list[dict[str, str]] = []
    attempts = 0
    max_attempts = target * 5
    while len(accepted_rows) < target and attempts < max_attempts:
        sample_index = attempts
        attempts += 1
        try:
            assembly = generate_sample(sample_index, spec.seed, spec.defect_rate)
            row = mesh_and_write_sample(assembly, output_dir, mesh_profile)
        except Exception as exc:
            rejections.append(
                {
                    "sample_id": f"sample_{sample_index:06d}",
                    "reason": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue
        if row["accepted"] and _synthetic_rejection_case(sample_index):
            row = _mark_synthetic_rejected(row, "synthetic_refinement_failure_case")
            rows.append(row)
            rejections.append(
                {
                    "sample_id": str(row["sample_id"]),
                    "reason": "synthetic_refinement_failure_case",
                    "message": "Deterministic synthetic failure case retained for failure-risk and repair-label training.",
                }
            )
        elif row["accepted"]:
            rows.append(row)
            accepted_rows.append(row)
        else:
            rows.append(row)
            rejections.append(
                {
                    "sample_id": str(row.get("sample_id", f"sample_{sample_index:06d}")),
                    "reason": "qa_rejected",
                    "message": "Synthetic oracle mesh quality gate rejected the sample.",
                }
            )
    if rejections:
        (output_dir / "rejection_log.json").write_text(json.dumps(rejections, indent=2, sort_keys=True), encoding="utf-8")
    if len(accepted_rows) < target:
        raise RuntimeError(f"accepted synthetic dataset target not reached: accepted={len(accepted_rows)} target={target} attempts={attempts}")
    sample_ids = [row["sample_id"] for row in accepted_rows]
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
        "accepted_count": len(accepted_rows),
        "rejected_count": len(rows) - len(accepted_rows),
        "splits": {name: len(ids) for name, ids in splits.items()},
        "backend": spec.backend,
        "acceptance_rate": len(accepted_rows) / attempts,
        "total_sample_count": len(rows),
        "synthetic_failure_case_count": len(rows) - len(accepted_rows),
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"manifest": manifest, "rows": rows}


def _synthetic_rejection_case(sample_index: int) -> bool:
    return sample_index > 0 and sample_index % 8 == 7


def _mark_synthetic_rejected(row: dict[str, Any], reason: str) -> dict[str, Any]:
    row = dict(row)
    row["accepted"] = False
    row["acceptance_status"] = "rejected"
    row["rejection_reason"] = reason
    qa_path = Path(row["qa_metrics_path"])
    if qa_path.exists():
        metrics = json.loads(qa_path.read_text(encoding="utf-8"))
        metrics["accepted"] = False
        metrics.setdefault("failed_regions", []).append({"reason": reason, "source": "synthetic_refinement_case"})
        metrics["synthetic_quality_case"] = reason
        qa_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    sample_dir = Path(row["sample_dir"])
    rejection_path = sample_dir / "mesh/report/synthetic_rejection.json"
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.write_text(
        json.dumps({"sample_id": row["sample_id"], "accepted": False, "reason": reason}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return row
