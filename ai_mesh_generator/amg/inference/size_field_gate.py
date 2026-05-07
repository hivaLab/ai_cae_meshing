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


def _semantic_maps(sample_dir: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    labels_path = sample_dir / "labels" / "edge_segmentation.json"
    signatures_path = sample_dir / "graph" / "entity_signatures.json"
    semantics: dict[str, str] = {}
    fingerprints: dict[str, dict[str, Any]] = {}
    if labels_path.is_file():
        document = _read_json(labels_path)
        semantics = {str(item["edge_signature_id"]): str(item["semantic_label"]) for item in document.get("labels", []) if isinstance(item, dict)}
    if signatures_path.is_file():
        document = _read_json(signatures_path)
        fingerprints = {
            str(item["signature_id"]): dict(item.get("fingerprint", {}))
            for item in document.get("edges", [])
            if isinstance(item, dict)
        }
    return semantics, fingerprints


def _fingerprint_xy_bounds(fingerprints: dict[str, dict[str, Any]]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for fingerprint in fingerprints.values():
        center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
        if center is not None and len(center) >= 2:
            xs.append(float(center[0]))
            ys.append(float(center[1]))
        points = fingerprint.get("vertex_points_mm") if isinstance(fingerprint.get("vertex_points_mm"), list) else []
        for point in points:
            if isinstance(point, list) and len(point) >= 2:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs or not ys:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _is_global_far_field_fingerprint(
    fingerprint: dict[str, Any],
    bounds: tuple[float, float, float, float] | None,
    *,
    h0_mm: float | None,
) -> bool:
    if bounds is None:
        return False
    if int(fingerprint.get("curve_type_id", 0) or 0) != 1:
        return False
    length = float(fingerprint.get("length_mm", 0.0) or 0.0)
    threshold = max(30.0, 6.0 * float(h0_mm)) if isinstance(h0_mm, (int, float)) else 30.0
    if length <= threshold:
        return False
    bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
    if bbox is not None and len(bbox) >= 3 and abs(float(bbox[2])) > 1.0e-6:
        return False
    center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
    if center is None or len(center) < 2:
        return False
    x_min, x_max, y_min, y_max = bounds
    x, y = float(center[0]), float(center[1])
    tolerance = max(1.0e-6, 1.0e-5 * max(abs(x_max - x_min), abs(y_max - y_min), 1.0))
    return abs(x - x_min) <= tolerance or abs(x - x_max) <= tolerance or abs(y - y_min) <= tolerance or abs(y - y_max) <= tolerance


def _semantic_size_stats(sample_dir: Path, edge_sizes: list[dict[str, Any]], *, default_h0_mm: float | None = None) -> dict[str, Any]:
    semantics, fingerprints = _semantic_maps(sample_dir)
    bounds = _fingerprint_xy_bounds(fingerprints)
    grouped: dict[str, list[float]] = {}
    far_values: list[float] = []
    hole_divisions: list[float] = []
    explicit_ids: set[str] = set()
    for item in edge_sizes:
        signature_id = str(item["edge_signature_id"])
        explicit_ids.add(signature_id)
        semantic = semantics.get(signature_id, "UNKNOWN")
        target = float(item["target_size_mm"])
        grouped.setdefault(semantic, []).append(target)
        fingerprint = fingerprints.get(signature_id, {})
        if semantic in {"OUTER_BOUNDARY", "FREE_EDGE"} and _is_global_far_field_fingerprint(fingerprint, bounds, h0_mm=default_h0_mm):
            far_values.append(target)
        if semantic == "HOLE_BOUNDARY" and int(fingerprint.get("curve_type_id", 0) or 0) in {2, 3}:
            bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
            if bbox is not None and len(bbox) >= 2:
                bx = abs(float(bbox[0]))
                by = abs(float(bbox[1]))
                if max(bx, by) > 0 and abs(bx - by) > 0.20 * max(bx, by):
                    continue
            length = float(fingerprint.get("length_mm", 0.0) or 0.0)
            if length > 0 and target > 0:
                hole_divisions.append(length / target)
    semantic_stats = {
        label: {
            "count": len(values),
            "min": min(values),
            "mean": mean(values),
            "max": max(values),
            "std": pstdev(values) if len(values) > 1 else 0.0,
        }
        for label, values in sorted(grouped.items())
    }
    if isinstance(default_h0_mm, (int, float)):
        for signature_id, semantic in semantics.items():
            fingerprint = fingerprints.get(signature_id, {})
            if (
                semantic in {"OUTER_BOUNDARY", "FREE_EDGE"}
                and signature_id not in explicit_ids
                and _is_global_far_field_fingerprint(fingerprint, bounds, h0_mm=default_h0_mm)
            ):
                grouped.setdefault(semantic, []).append(float(default_h0_mm))
                far_values.append(float(default_h0_mm))
    return {
        "by_semantic": semantic_stats,
        "far_field_edge_mean": mean(far_values) if far_values else None,
        "hole_boundary_divisions": {
            "count": len(hole_divisions),
            "min": min(hole_divisions) if hole_divisions else None,
            "mean": mean(hole_divisions) if hole_divisions else None,
            "max": max(hole_divisions) if hole_divisions else None,
        },
    }


def _efficiency_failure_reason(
    *,
    semantic_stats: dict[str, Any],
    shell_element_count: Any,
    require_efficiency: bool,
) -> str | None:
    if not require_efficiency:
        return None
    far_mean = semantic_stats.get("far_field_edge_mean")
    if isinstance(far_mean, (int, float)) and float(far_mean) < 3.0:
        return "far_field_over_refined"
    hole = semantic_stats.get("hole_boundary_divisions", {})
    if isinstance(hole, dict) and hole.get("count", 0):
        minimum = hole.get("min")
        maximum = hole.get("max")
        if isinstance(minimum, (int, float)) and minimum < 24.0:
            return "hole_boundary_under_resolved"
        if isinstance(maximum, (int, float)) and maximum > 48.0:
            return "hole_boundary_over_refined"
    if isinstance(shell_element_count, (int, float)) and hole.get("count", 0) and shell_element_count > 113171:
        return "shell_element_count_not_improved"
    return None


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
    require_efficiency: bool = False,
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
    edge_size_records = list(size_field.get("edge_sizes", []))
    edge_stats = _size_stats(edge_size_records, h_min_mm=global_mesh.get("h_min_mm"))
    semantic_stats = _semantic_size_stats(sample, edge_size_records, default_h0_mm=global_mesh.get("h0_mm"))
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
    mesh_stats = quality.get("mesh_stats", {}) if isinstance(quality.get("mesh_stats"), dict) else {}
    efficiency_failure = _efficiency_failure_reason(
        semantic_stats=semantic_stats,
        shell_element_count=mesh_stats.get("shell_element_count"),
        require_efficiency=require_efficiency,
    )
    success = mesh_success and not all_h_min and efficiency_failure is None
    if success:
        status = "SUCCESS"
        failure_reason = None
    elif mesh_success and all_h_min:
        status = "FAILED_LEARNING_SIGNAL"
        failure_reason = "all_controlled_edges_at_h_min"
    elif mesh_success and efficiency_failure is not None:
        status = "FAILED_EFFICIENCY_SIGNAL"
        failure_reason = efficiency_failure
    else:
        status = "FAILED"
        failure_reason = "real_ai_size_field_gate_failed"
    quality_metrics = quality.get("quality", {}) if isinstance(quality.get("quality"), dict) else {}
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
        "semantic_edge_target_size_stats": semantic_stats,
        "over_refinement": {
            "all_controlled_edges_at_h_min": all_h_min,
            "h_min_edge_fraction": edge_stats["h_min_edge_fraction"],
            "efficiency_failure_reason": efficiency_failure,
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
    parser.add_argument("--require-efficiency", action="store_true")
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
            require_efficiency=args.require_efficiency,
        )
        result = write_ai_size_field_gate_report(args.out, report)
    except (AiSizeFieldGateError, OSError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": result.status, "report": Path(args.out).as_posix()})
    return 0 if result.status == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
