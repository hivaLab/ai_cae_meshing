"""AMG-side report builder for the real AI size-field gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Sequence


class AiSizeFieldGateError(ValueError):
    """Raised when an AI size-field gate report cannot be built from real artifacts."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AiSizeFieldGateResult:
    status: str
    sample_id: str
    report_path: Path | None
    max_boundary_size_error: float | None
    hard_fail_count: int


def _read_json(path: str | Path) -> dict[str, Any]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AiSizeFieldGateError("json_not_object", f"expected JSON object: {path}")
    return loaded


def _optional_json(path: Path) -> dict[str, Any] | None:
    return _read_json(path) if path.is_file() else None


def _size_stats(edge_sizes: list[dict[str, Any]], *, h_min_mm: float | None = None) -> dict[str, Any]:
    values = [float(item["target_size_mm"]) for item in edge_sizes]
    if not values:
        raise AiSizeFieldGateError("empty_size_field", "predicted size field has no edge sizes")
    h_min = min(values) if h_min_mm is None else float(h_min_mm)
    return {
        "min": min(values),
        "mean": mean(values),
        "max": max(values),
        "std": pstdev(values) if len(values) > 1 else 0.0,
        "count": len(values),
        "h_min_edge_fraction": sum(1 for value in values if abs(value - h_min) <= max(1.0e-9, h_min * 1.0e-6)) / len(values),
    }


def _quality_stats(entity_quality: dict[str, Any]) -> dict[str, Any]:
    rows = entity_quality.get("entity_quality", [])
    if not isinstance(rows, list) or not rows:
        raise AiSizeFieldGateError("missing_entity_quality_rows", "entity quality report has no rows")
    available = [row for row in rows if isinstance(row, dict) and row.get("metric_available")]
    unavailable = len(rows) - len(available)
    boundary_errors = [float(row["measured_boundary_size_error"]) for row in available if "measured_boundary_size_error" in row]
    hard_fail_count = sum(1 for row in rows if isinstance(row, dict) and row.get("hard_fail"))
    return {
        "entity_row_count": len(rows),
        "metric_available_count": len(available),
        "metric_unavailable_count": unavailable,
        "hard_fail_count": hard_fail_count,
        "max_boundary_size_error": max(boundary_errors) if boundary_errors else None,
        "mean_boundary_size_error": mean(boundary_errors) if boundary_errors else None,
    }


def _split_count(dataset_root: Path, split: str) -> int:
    split_path = dataset_root / "splits" / f"{split}.txt"
    if not split_path.is_file():
        return 0
    return len([line for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _sample_part_class(sample_dir: Path) -> str | None:
    path = sample_dir / "metadata" / "part_class_label.json"
    if not path.is_file():
        return None
    document = _read_json(path)
    part_class = document.get("part_class")
    return str(part_class) if isinstance(part_class, str) else None


def build_ai_size_field_gate_report(
    *,
    dataset_root: str | Path,
    sample_dir: str | Path,
    train_split: str,
    part_classifier_path: str | Path,
    segmentation_checkpoint_path: str | Path,
    size_field_checkpoint_path: str | Path,
    predicted_size_field_path: str | Path,
    ansa_eval_dir: str | Path,
) -> dict[str, Any]:
    dataset = Path(dataset_root)
    sample = Path(sample_dir)
    eval_dir = Path(ansa_eval_dir)
    size_field = _read_json(predicted_size_field_path)
    context = _optional_json(Path(predicted_size_field_path).with_name("ai_size_field_context.json")) or {}
    execution = _read_json(eval_dir / "reports" / "ansa_execution_report.json")
    quality = _read_json(eval_dir / "reports" / "ansa_quality_report.json")
    entity_quality = _read_json(eval_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json")
    mesh_path = eval_dir / "meshes" / "ansa_size_field_mesh.bdf"
    local = _quality_stats(entity_quality)
    global_mesh = size_field.get("global_mesh", {}) if isinstance(size_field.get("global_mesh"), dict) else {}
    edge_stats = _size_stats(list(size_field.get("edge_sizes", [])), h_min_mm=global_mesh.get("h_min_mm"))
    mesh_ok = mesh_path.is_file() and mesh_path.stat().st_size > 0
    hard_failed_elements = quality.get("quality", {}).get("num_hard_failed_elements") if isinstance(quality.get("quality"), dict) else None
    mesh_success = (
        execution.get("accepted") is True
        and quality.get("accepted") is True
        and hard_failed_elements == 0
        and mesh_ok
        and local["metric_unavailable_count"] == 0
        and local["hard_fail_count"] == 0
    )
    all_h_min = edge_stats["h_min_edge_fraction"] >= 1.0
    success = mesh_success and not all_h_min
    if success:
        status = "SUCCESS"
        failure_reason = None
    elif mesh_success and all_h_min:
        status = "FAILED_LEARNING_SIGNAL"
        failure_reason = "all_controlled_edges_at_h_min"
    else:
        status = "FAILED"
        failure_reason = "real_ai_size_field_gate_failed"
    quality_metrics = quality.get("quality", {}) if isinstance(quality.get("quality"), dict) else {}
    mesh_stats = quality.get("mesh_stats", {}) if isinstance(quality.get("mesh_stats"), dict) else {}
    return {
        "schema": "AMG_AI_SIZE_FIELD_GATE_REPORT_V1",
        "status": status,
        "attempted_count": 1,
        "valid_mesh_count": 1 if mesh_success else 0,
        "dataset_root": dataset.as_posix(),
        "train_split": train_split,
        "train_split_sample_count": _split_count(dataset, train_split),
        "held_out_sample_id": sample.name,
        "held_out_part_class": _sample_part_class(sample),
        "held_out_family_group": "flat" if _sample_part_class(sample) == "SM_FLAT_PANEL" else "bent",
        "model_paths": {
            "part_classifier": Path(part_classifier_path).as_posix(),
            "segmentation": Path(segmentation_checkpoint_path).as_posix(),
            "size_field": Path(size_field_checkpoint_path).as_posix(),
        },
        "predicted_size_field_path": Path(predicted_size_field_path).as_posix(),
        "part_prediction": context.get("part_prediction"),
        "segmentation_histograms": {
            "face": context.get("face_segmentation_histogram"),
            "edge": context.get("edge_segmentation_histogram"),
        },
        "edge_target_size_stats": edge_stats,
        "over_refinement": {
            "all_controlled_edges_at_h_min": all_h_min,
            "h_min_edge_fraction": edge_stats["h_min_edge_fraction"],
        },
        "ansa_reports": {
            "execution_report": (eval_dir / "reports" / "ansa_execution_report.json").as_posix(),
            "quality_report": (eval_dir / "reports" / "ansa_quality_report.json").as_posix(),
            "entity_quality": (eval_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json").as_posix(),
            "mesh": mesh_path.as_posix(),
        },
        "entity_local_quality": local,
        "shell_element_count": mesh_stats.get("shell_element_count"),
        "num_hard_failed_elements": quality_metrics.get("num_hard_failed_elements"),
        "mesh_bytes": mesh_path.stat().st_size if mesh_ok else 0,
        "failure_reason": failure_reason,
    }


def write_ai_size_field_gate_report(path: str | Path, report: dict[str, Any]) -> AiSizeFieldGateResult:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    local = report.get("entity_local_quality", {}) if isinstance(report.get("entity_local_quality"), dict) else {}
    return AiSizeFieldGateResult(
        status=str(report["status"]),
        sample_id=str(report["held_out_sample_id"]),
        report_path=output,
        max_boundary_size_error=local.get("max_boundary_size_error"),
        hard_fail_count=int(local.get("hard_fail_count", 0)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-size-field-gate-report")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--part-classifier", required=True)
    parser.add_argument("--segmentation-checkpoint", required=True)
    parser.add_argument("--size-field-checkpoint", required=True)
    parser.add_argument("--predicted-size-field", required=True)
    parser.add_argument("--ansa-eval-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        report = build_ai_size_field_gate_report(
            dataset_root=args.dataset,
            sample_dir=args.sample_dir,
            train_split=args.train_split,
            part_classifier_path=args.part_classifier,
            segmentation_checkpoint_path=args.segmentation_checkpoint,
            size_field_checkpoint_path=args.size_field_checkpoint,
            predicted_size_field_path=args.predicted_size_field,
            ansa_eval_dir=args.ansa_eval_dir,
        )
        result = write_ai_size_field_gate_report(args.out, report)
    except (AiSizeFieldGateError, OSError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": result.status, "report": Path(args.out).as_posix()})
    return 0 if result.status == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
