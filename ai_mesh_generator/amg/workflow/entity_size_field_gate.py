"""Primary end-to-end AMG entity size-field gate.

This module intentionally calls CDF/ANSA evaluation through a subprocess
contract.  AMG code owns model training/inference and reads produced files; it
does not import CDF Python packages.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from ai_mesh_generator.amg.inference.size_field import infer_size_field_document
from ai_mesh_generator.amg.inference.size_field import build_ai_size_field_context
from ai_mesh_generator.amg.inference.size_field_gate import AiSizeFieldGateError, build_ai_size_field_gate_report, write_ai_size_field_gate_report
from ai_mesh_generator.amg.dataset import load_entity_dataset_sample
from ai_mesh_generator.amg.model.segmentation import EDGE_SEGMENTATION_CLASSES, FACE_SEGMENTATION_CLASSES
from ai_mesh_generator.amg.model.size_field import write_size_field_document
from ai_mesh_generator.amg.training._entity_common import iter_entity_sample_dirs, write_json
from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset
from ai_mesh_generator.amg.training.size_field import train_size_field_model


class EntitySizeFieldWorkflowError(ValueError):
    """Raised when the primary AI size-field workflow cannot run."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _evaluate_size_field_command(
    *,
    sample_dir: Path,
    size_field_path: Path,
    out_dir: Path,
    ansa_executable: str,
    timeout_sec: int,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "cad_dataset_factory.cdf.entity_cli",
        "ansa-evaluate-size-field",
        "--sample-dir",
        str(sample_dir),
        "--size-field",
        str(size_field_path),
        "--out",
        str(out_dir),
        "--ansa-executable",
        ansa_executable,
        "--timeout-sec",
        str(timeout_sec),
    ]


def _run_ansa_size_field_evaluation(
    *,
    sample_dir: Path,
    size_field_path: Path,
    out_dir: Path,
    ansa_executable: str,
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    command = _evaluate_size_field_command(
        sample_dir=sample_dir,
        size_field_path=size_field_path,
        out_dir=out_dir,
        ansa_executable=ansa_executable,
        timeout_sec=timeout_sec,
    )
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout_sec + 30, check=False)


def _counter_from_reports(reports: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for report in reports:
        value = report.get(key)
        if isinstance(value, str):
            counter[value] += 1
    return dict(counter)


def _aggregate_gate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    edge_std_values = [float(report["edge_target_size_stats"]["std"]) for report in reports if isinstance(report.get("edge_target_size_stats"), dict)]
    h_min_fractions = [float(report["edge_target_size_stats"]["h_min_edge_fraction"]) for report in reports if isinstance(report.get("edge_target_size_stats"), dict)]
    return {
        "attempted_count": len(reports),
        "valid_mesh_count": sum(int(report.get("valid_mesh_count", 0)) for report in reports),
        "success_count": sum(1 for report in reports if report.get("status") == "SUCCESS"),
        "status_counts": _counter_from_reports(reports, "status"),
        "failure_reason_counts": _counter_from_reports(reports, "failure_reason"),
        "edge_size_std_min": min(edge_std_values) if edge_std_values else None,
        "edge_size_std_mean": sum(edge_std_values) / len(edge_std_values) if edge_std_values else None,
        "h_min_edge_fraction_max": max(h_min_fractions) if h_min_fractions else None,
    }


def _probability_histogram(probabilities: Any, classes: tuple[str, ...]) -> dict[str, int]:
    labels = probabilities.argmax(axis=1)
    return {label: int((labels == index).sum()) for index, label in enumerate(classes)}


def _write_context_file(sample_dir: Path, output_path: Path, part_classifier_path: Path, segmentation_checkpoint_path: Path) -> None:
    sample = load_entity_dataset_sample(sample_dir)
    context = build_ai_size_field_context(
        sample=sample,
        part_classifier_path=part_classifier_path,
        segmentation_checkpoint_path=segmentation_checkpoint_path,
    )
    write_json(
        output_path,
        {
            "schema": "AMG_AI_SIZE_FIELD_CONTEXT_V1",
            "part_prediction": context.part_prediction,
            "face_segmentation_histogram": _probability_histogram(context.face_segmentation_probabilities, FACE_SEGMENTATION_CLASSES),
            "edge_segmentation_histogram": _probability_histogram(context.edge_segmentation_probabilities, EDGE_SEGMENTATION_CLASSES),
        },
    )


def run_entity_size_field_gate_workflow(
    *,
    dataset: str | Path,
    ansa_executable: str,
    out: str | Path,
    train_split: str = "train",
    test_split: str = "test",
    part_split: str | None = None,
    part_eval_split: str | None = None,
    segmentation_split: str | None = None,
    segmentation_eval_split: str | None = None,
    epochs_segmentation: int = 30,
    epochs_size_field: int = 40,
    seed: int = 1,
    h0_mm: float = 3.0,
    h_min_mm: float = 0.5,
    h_max_mm: float = 8.0,
    growth_rate: float = 1.25,
    timeout_sec: int = 300,
    limit: int | None = None,
    require_efficiency: bool = False,
) -> dict[str, Any]:
    dataset_root = Path(dataset)
    output_root = Path(out)
    output_root.mkdir(parents=True, exist_ok=True)
    sample_dirs = iter_entity_sample_dirs(dataset_root, split=test_split)
    if limit is not None:
        sample_dirs = sample_dirs[:limit]
    if not sample_dirs:
        raise EntitySizeFieldWorkflowError("empty_test_split", f"no samples found in split {test_split}")
    part_split = part_split or ("part_train" if (dataset_root / "splits" / "part_train.txt").is_file() else train_split)
    part_eval_split = part_eval_split or ("part_test" if (dataset_root / "splits" / "part_test.txt").is_file() else None)
    segmentation_split = segmentation_split or ("segmentation_train" if (dataset_root / "splits" / "segmentation_train.txt").is_file() else train_split)
    segmentation_eval_split = segmentation_eval_split or ("segmentation_test" if (dataset_root / "splits" / "segmentation_test.txt").is_file() else None)

    part_dir = output_root / "part_classifier"
    seg_dir = output_root / "segmentation"
    size_dir = output_root / "size_field"
    part_metrics = train_part_classifier_from_dataset(dataset_root, part_dir, split=part_split, eval_split=part_eval_split, seed=seed, uncertainty_threshold=0.0)
    segmentation_metrics = train_entity_segmentation_from_dataset(dataset_root, seg_dir, split=segmentation_split, eval_split=segmentation_eval_split, epochs=epochs_segmentation, seed=seed)
    size_metrics = train_size_field_model(
        dataset_root,
        size_dir,
        split=train_split,
        epochs=epochs_size_field,
        seed=seed,
        prefer_quality_evidence=True,
        part_classifier_path=part_dir / "model.pkl",
        segmentation_checkpoint_path=seg_dir / "model.pt",
        use_predicted_context=True,
    )

    sample_reports: list[dict[str, Any]] = []
    subprocess_records: list[dict[str, Any]] = []
    for sample_dir in sample_dirs:
        sample_id = sample_dir.name
        size_field_path = output_root / "inference" / sample_id / "amg_size_field_ai.json"
        try:
            document = infer_size_field_document(
                sample_dir=sample_dir,
                checkpoint_path=size_dir / "model.pt",
                part_classifier_path=part_dir / "model.pkl",
                segmentation_checkpoint_path=seg_dir / "model.pt",
                h0_mm=h0_mm,
                h_min_mm=h_min_mm,
                h_max_mm=h_max_mm,
                growth_rate=growth_rate,
            )
            write_size_field_document(size_field_path, document)
            _write_context_file(sample_dir, size_field_path.with_name("ai_size_field_context.json"), part_dir / "model.pkl", seg_dir / "model.pt")
            eval_dir = output_root / "ansa_eval" / sample_id
            completed = _run_ansa_size_field_evaluation(
                sample_dir=sample_dir,
                size_field_path=size_field_path,
                out_dir=eval_dir,
                ansa_executable=ansa_executable,
                timeout_sec=timeout_sec,
            )
            subprocess_records.append(
                {
                    "sample_id": sample_id,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
            )
            report = build_ai_size_field_gate_report(
                dataset_root=dataset_root,
                sample_dir=sample_dir,
                train_split=train_split,
                part_classifier_path=part_dir / "model.pkl",
                segmentation_checkpoint_path=seg_dir / "model.pt",
                size_field_checkpoint_path=size_dir / "model.pt",
                predicted_size_field_path=size_field_path,
                ansa_eval_dir=eval_dir,
                require_efficiency=require_efficiency,
            )
            write_ai_size_field_gate_report(output_root / "gate_reports" / f"{sample_id}.json", report)
        except (AiSizeFieldGateError, EntitySizeFieldWorkflowError, ValueError, OSError, subprocess.SubprocessError) as exc:
            report = {
                "schema": "AMG_AI_SIZE_FIELD_GATE_REPORT_V1",
                "status": "BLOCKED",
                "held_out_sample_id": sample_id,
                "failure_reason": type(exc).__name__ if not hasattr(exc, "code") else getattr(exc, "code"),
                "message": str(exc),
            }
            write_json(output_root / "gate_reports" / f"{sample_id}.json", report)
        sample_reports.append(report)

    aggregate = _aggregate_gate_reports(sample_reports)
    status = (
        "SUCCESS"
        if aggregate["success_count"] == aggregate["attempted_count"] and size_metrics.get("learning_signal_status") == "SUCCESS"
        else "FAILED"
    )
    workflow_report = {
        "schema": "AMG_ENTITY_SIZE_FIELD_WORKFLOW_REPORT_V1",
        "status": status,
        "dataset_root": dataset_root.as_posix(),
        "output_root": output_root.as_posix(),
        "train_split": train_split,
        "test_split": test_split,
        "part_split": part_split,
        "part_eval_split": part_eval_split,
        "segmentation_split": segmentation_split,
        "segmentation_eval_split": segmentation_eval_split,
        "model_metrics": {
            "part_classifier": part_metrics,
            "segmentation": segmentation_metrics,
            "size_field": size_metrics,
        },
        "gate": aggregate,
        "require_efficiency": require_efficiency,
        "sample_reports": sample_reports,
        "subprocess_records": subprocess_records,
    }
    write_json(output_root / "workflow_report.json", workflow_report)
    return workflow_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-entity-size-field-gate")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--ansa-executable", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--test-split", default="test")
    parser.add_argument("--part-split")
    parser.add_argument("--part-eval-split")
    parser.add_argument("--segmentation-split")
    parser.add_argument("--segmentation-eval-split")
    parser.add_argument("--epochs-segmentation", type=int, default=30)
    parser.add_argument("--epochs-size-field", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--h0-mm", type=float, default=3.0)
    parser.add_argument("--h-min-mm", type=float, default=0.5)
    parser.add_argument("--h-max-mm", type=float, default=8.0)
    parser.add_argument("--growth-rate", type=float, default=1.25)
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--require-efficiency", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_entity_size_field_gate_workflow(
            dataset=args.dataset,
            ansa_executable=args.ansa_executable,
            out=args.out,
            train_split=args.train_split,
            test_split=args.test_split,
            part_split=args.part_split,
            part_eval_split=args.part_eval_split,
            segmentation_split=args.segmentation_split,
            segmentation_eval_split=args.segmentation_eval_split,
            epochs_segmentation=args.epochs_segmentation,
            epochs_size_field=args.epochs_size_field,
            seed=args.seed,
            h0_mm=args.h0_mm,
            h_min_mm=args.h_min_mm,
            h_max_mm=args.h_max_mm,
            growth_rate=args.growth_rate,
            timeout_sec=args.timeout_sec,
            limit=args.limit,
            require_efficiency=args.require_efficiency,
        )
    except (EntitySizeFieldWorkflowError, ValueError, OSError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": report["status"], "workflow_report": (Path(args.out) / "workflow_report.json").as_posix()})
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
