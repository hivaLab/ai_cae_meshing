"""Real ANSA size-field sweep utilities for CDF v2 entity datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cad_dataset_factory.cdf.oracle import AnsaSizeFieldEvaluationRequest, run_ansa_size_field_evaluation


class EntitySizeSweepError(ValueError):
    """Raised when an entity size-field sweep cannot be built or executed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SizeSweepVariant:
    evaluation_id: str
    variant: str
    size_field_path: Path
    document: dict[str, Any]


@dataclass(frozen=True)
class EntitySizeSweepResult:
    status: str
    dataset_root: Path
    attempted_count: int
    completed_count: int
    failed_count: int
    blocked_count: int
    records: tuple[dict[str, Any], ...]
    summary_path: Path
    exit_code: int


SWEEP_FACTORS: tuple[tuple[str, float | None], ...] = (
    ("h_min_overrefined", 0.0),
    ("fine", 0.75),
    ("nominal", 1.0),
    ("coarse", 3.0),
)

EFFICIENCY_VARIANTS = (
    "h_min_overrefined",
    "feature_fine_far_nominal",
    "balanced",
    "far_coarse",
    "coarse_stress_test",
)


def _read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise EntitySizeSweepError("json_not_object", f"{path.as_posix()} must contain an object")
    return loaded


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dataset_sample_dirs(dataset_root: Path, split: str | None, sample_id: str | None) -> list[Path]:
    samples_root = dataset_root / "samples"
    if sample_id:
        sample_dir = samples_root / sample_id
        if not sample_dir.is_dir():
            raise EntitySizeSweepError("missing_sample", f"sample does not exist: {sample_id}")
        return [sample_dir]
    if split:
        split_path = dataset_root / "splits" / f"{split}.txt"
        if not split_path.is_file():
            raise EntitySizeSweepError("missing_split", f"split file does not exist: {split_path.as_posix()}")
        ids = [line.strip() for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        sample_dirs = [samples_root / item for item in ids]
    else:
        sample_dirs = sorted(path for path in samples_root.glob("sample_*") if path.is_dir())
    missing = [path.name for path in sample_dirs if not path.is_dir()]
    if missing:
        raise EntitySizeSweepError("missing_split_sample", f"split references missing samples: {', '.join(missing)}")
    return sample_dirs


def _variant_target(base_target: float, global_mesh: dict[str, Any], factor: float | None) -> float:
    h_min = float(global_mesh["h_min_mm"])
    h_max = float(global_mesh["h_max_mm"])
    h0 = float(global_mesh["h0_mm"])
    if factor == 0.0:
        return h_min
    if factor is None:
        return float(base_target)
    return max(h_min, min(h_max, max(base_target * factor, h0 * factor if factor > 1.0 else base_target * factor)))


def _edge_semantics(sample_path: Path) -> dict[str, str]:
    path = sample_path / "labels" / "edge_segmentation.json"
    if not path.is_file():
        return {}
    document = _read_json(path)
    return {str(item["edge_signature_id"]): str(item["semantic_label"]) for item in document.get("labels", []) if isinstance(item, dict)}


def _is_feature_boundary(semantic: str) -> bool:
    return semantic in {"HOLE_BOUNDARY", "SLOT_BOUNDARY", "CUTOUT_BOUNDARY"}


def _efficiency_variant_target(base_target: float, global_mesh: dict[str, Any], semantic: str, variant: str) -> float:
    h_min = float(global_mesh["h_min_mm"])
    h_max = float(global_mesh["h_max_mm"])
    h0 = float(global_mesh["h0_mm"])
    if variant == "h_min_overrefined":
        return h_min
    if variant == "feature_fine_far_nominal":
        return max(h_min, min(h_max, base_target * 0.75 if _is_feature_boundary(semantic) else h0))
    if variant == "balanced":
        return max(h_min, min(h_max, base_target if _is_feature_boundary(semantic) or semantic == "BEND_EDGE" else h0))
    if variant == "far_coarse":
        far = min(h_max, h0 * 1.5)
        return max(h_min, min(h_max, base_target if _is_feature_boundary(semantic) or semantic == "BEND_EDGE" else far))
    if variant == "coarse_stress_test":
        if _is_feature_boundary(semantic):
            return max(h_min, min(h_max, max(base_target * 2.0, h0)))
        return h_max
    raise EntitySizeSweepError("unsupported_efficiency_variant", f"unknown efficiency variant: {variant}")


def build_size_sweep_variants(sample_dir: str | Path, *, preset: str = "local_quality_v1") -> tuple[SizeSweepVariant, ...]:
    """Build schema-valid size-field variants without running ANSA."""

    if preset not in {"local_quality_v1", "local_efficiency_v1"}:
        raise EntitySizeSweepError("unsupported_preset", "supported presets: local_quality_v1, local_efficiency_v1")
    sample_path = Path(sample_dir)
    base = _read_json(sample_path / "labels" / "mesh_size_field.json")
    global_mesh = dict(base["global_mesh"])
    semantics = _edge_semantics(sample_path)
    variants: list[SizeSweepVariant] = []
    names = tuple(name for name, _factor in SWEEP_FACTORS) if preset == "local_quality_v1" else EFFICIENCY_VARIANTS
    for index, variant_name in enumerate(names, start=1):
        factor = dict(SWEEP_FACTORS).get(variant_name)
        evaluation_id = f"sweep_{index:02d}_{variant_name}"
        edge_sizes = []
        for edge in base.get("edge_sizes", []):
            semantic = semantics.get(str(edge["edge_signature_id"]), "OTHER")
            target = (
                _variant_target(float(edge["target_size_mm"]), global_mesh, factor)
                if preset == "local_quality_v1"
                else _efficiency_variant_target(float(edge["target_size_mm"]), global_mesh, semantic, variant_name)
            )
            edge_sizes.append(
                {
                    "edge_signature_id": edge["edge_signature_id"],
                    "target_size_mm": target,
                    "source": f"cdf_entity_size_sweep:{variant_name}",
                }
            )
        document = {
            "schema_version": "AMG_SIZE_FIELD_SM_V2",
            "sample_id": base["sample_id"],
            "cad_file": base.get("cad_file", "cad/input.step"),
            "unit": "mm",
            "global_mesh": global_mesh,
            "edge_sizes": edge_sizes,
            "face_sizes": [
                {
                    "face_signature_id": face["face_signature_id"],
                    "target_size_mm": _variant_target(float(face["target_size_mm"]), global_mesh, factor if preset == "local_quality_v1" else 1.0),
                    "source": f"cdf_entity_size_sweep:{variant_name}",
                }
                for face in base.get("face_sizes", [])
            ],
        }
        path = sample_path / "quality_evaluations" / evaluation_id / "size_field.json"
        variants.append(SizeSweepVariant(evaluation_id, variant_name, path, document))
    return tuple(variants)


def write_size_sweep_variants(sample_dir: str | Path, *, preset: str = "local_quality_v1") -> tuple[SizeSweepVariant, ...]:
    variants = build_size_sweep_variants(sample_dir, preset=preset)
    for variant in variants:
        _write_json(variant.size_field_path, variant.document)
    return variants


def run_entity_size_sweep(
    dataset_root: str | Path,
    *,
    ansa_executable: str,
    split: str | None = None,
    sample_id: str | None = None,
    preset: str = "local_quality_v1",
    limit: int | None = None,
    timeout_sec: int = 300,
) -> EntitySizeSweepResult:
    root = Path(dataset_root)
    sample_dirs = _dataset_sample_dirs(root, split, sample_id)
    if limit is not None:
        sample_dirs = sample_dirs[: max(0, limit)]
    records: list[dict[str, Any]] = []
    completed = failed = blocked = attempted = 0
    for sample_dir in sample_dirs:
        for variant in write_size_sweep_variants(sample_dir, preset=preset):
            attempted += 1
            eval_dir = sample_dir / "quality_evaluations" / variant.evaluation_id
            result = run_ansa_size_field_evaluation(
                AnsaSizeFieldEvaluationRequest(
                    sample_dir=sample_dir,
                    size_field_path=variant.size_field_path,
                    ansa_executable=ansa_executable,
                    out_dir=eval_dir,
                    execution_report_path=eval_dir / "reports" / "ansa_execution_report.json",
                    quality_report_path=eval_dir / "reports" / "ansa_quality_report.json",
                    entity_quality_path=eval_dir / "entity_quality_labels.json",
                    mesh_path=eval_dir / "meshes" / "ansa_size_field_mesh.bdf",
                    diagnostics_path=eval_dir / "reports" / "ansa_size_field_diagnostics.json",
                    evaluation_id=variant.evaluation_id,
                    timeout_sec=timeout_sec,
                )
            )
            if result.status == "COMPLETED":
                completed += 1
            elif result.status in {"BLOCKED", "TIMEOUT"}:
                blocked += 1
            else:
                failed += 1
            records.append(
                {
                    "sample_id": sample_dir.name,
                    "evaluation_id": variant.evaluation_id,
                    "variant": variant.variant,
                    "status": result.status,
                    "returncode": result.returncode,
                    "size_field_path": variant.size_field_path.as_posix(),
                    "execution_report": result.execution_report_path.as_posix(),
                    "quality_report": result.quality_report_path.as_posix(),
                    "entity_quality": result.entity_quality_path.as_posix(),
                    "mesh": result.mesh_path.as_posix(),
                    "error_code": result.error_code,
                }
            )
    status = "SUCCESS" if attempted and completed == attempted else "IN_PROGRESS" if attempted else "BLOCKED"
    summary = {
        "schema": "CDF_ENTITY_SIZE_FIELD_SWEEP_SUMMARY_V1",
        "dataset_root": root.as_posix(),
        "preset": preset,
        "split": split,
        "sample_id": sample_id,
        "attempted_count": attempted,
        "completed_count": completed,
        "failed_count": failed,
        "blocked_count": blocked,
        "records": records,
        "status": status,
    }
    summary_path = root / "size_field_sweep_summary.json"
    _write_json(summary_path, summary)
    return EntitySizeSweepResult(status, root, attempted, completed, failed, blocked, tuple(records), summary_path, 0 if status == "SUCCESS" else 2)
