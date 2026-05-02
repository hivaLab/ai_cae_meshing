from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ai_mesh_generator.meshing.ansa_runner import AnsaCommandBackend
from ai_mesh_generator.output.result_packager import validate_result_package
from ai_mesh_generator.workflow.run_mesh_job import run_mesh_job


QUALITY_PASS_STATUSES = {"pass", "passed", "passed_no_repair_required", "passed_after_repair"}


def default_dataset_dir(root: Path) -> Path:
    return root / "runs" / "full_delivery" / "CAE_MESH_DATASET_V001"


def default_model_path(root: Path) -> Path:
    return root / "runs" / "full_delivery" / "artifacts" / "models" / "amg_deployment_model.pt"


def load_regression_inputs(dataset_dir: Path | str, sample_count: int) -> list[dict[str, Any]]:
    dataset = Path(dataset_dir)
    split_path = dataset / "splits" / "test.txt"
    index_path = dataset / "dataset_index.parquet"
    if not split_path.exists():
        raise FileNotFoundError(f"test split file is missing: {split_path}")
    if not index_path.exists():
        raise FileNotFoundError(f"dataset index is missing: {index_path}")
    test_ids = [line.strip() for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected_ids = test_ids[: int(sample_count)]
    frame = pd.read_parquet(index_path)
    rows_by_id = {str(row["sample_id"]): row.to_dict() for _, row in frame.iterrows()}
    rows = []
    for sample_id in selected_ids:
        row = rows_by_id.get(sample_id)
        if row is None:
            raise KeyError(f"test split sample {sample_id} is missing from dataset_index.parquet")
        rows.append(row)
    return rows


def run_ansa_regression(
    dataset_dir: Path | str,
    model_path: Path | str,
    output_dir: Path | str,
    sample_count: int = 10,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    dataset = Path(dataset_dir)
    model = Path(model_path)
    output = Path(output_dir)
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not dataset.exists():
        raise FileNotFoundError(f"dataset directory is missing: {dataset}")
    if not model.exists():
        raise FileNotFoundError(f"model artifact is missing: {model}")
    ansa_status = AnsaCommandBackend().status()
    if not ansa_status["available"]:
        raise RuntimeError(f"ANSA backend is not available: {ansa_status}")

    output.mkdir(parents=True, exist_ok=True)
    rows = load_regression_inputs(dataset, sample_count)
    sample_results = []
    for index, row in enumerate(rows, start=1):
        sample_id = str(row["sample_id"])
        sample_dir = output / "samples" / f"{index:03d}_{sample_id}"
        result_zip = sample_dir / "MESH_RESULT.zip"
        sample_results.append(_run_one_sample(sample_id, Path(str(row["input_zip"])), model, result_zip))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_dir": str(dataset.resolve()),
        "model_path": str(model.resolve()),
        "output_dir": str(output.resolve()),
        "sample_count_requested": int(sample_count),
        "sample_count": len(sample_results),
        "ansa_backend": ansa_status,
        "samples": sample_results,
    }
    report["summary"] = summarize_regression(sample_results)
    write_regression_reports(report, output, root)
    return report


def _run_one_sample(sample_id: str, input_zip: Path, model_path: Path, result_zip: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        summary = run_mesh_job(input_zip, model_path, result_zip, backend="ANSA_BATCH")
        validation = validate_result_package(result_zip)
        row = extract_sample_result(sample_id, summary, validation, time.perf_counter() - started, "")
    except Exception as exc:
        row = failed_sample_result(sample_id, result_zip, time.perf_counter() - started, str(exc))
    return row


def extract_sample_result(
    sample_id: str,
    summary: dict[str, Any],
    validation: dict[str, Any],
    runtime_seconds: float,
    failure_reason: str,
) -> dict[str, Any]:
    metrics = summary.get("mesh_result", {}).get("metrics", {})
    manifest = metrics.get("ansa_manifest", {})
    recipe_summary = metrics.get("ansa_recipe_summary", {}) or manifest.get("ansa_recipe_application", {}).get("summary", {})
    native = metrics.get("native_entity_generation", {}) or manifest.get("native_entity_generation", {})
    quality_loop = metrics.get("ansa_quality_repair_loop", {}) or manifest.get("ansa_quality_repair_loop", {})
    traceability = metrics.get("bdf_traceability", {})
    deck = manifest.get("solver_deck_recipe_application", {})
    batch_sessions = manifest.get("ansa_recipe_application", {}).get("batch_mesh_sessions", {})
    batch_quality = batch_sessions.get("quality_summary", {})
    final_quality = final_quality_summary(batch_quality, quality_loop)
    bdf = validation.get("bdf_validation", {})
    expected = expected_counts(recipe_summary)
    result = {
        "sample_id": sample_id,
        "ansa_success": True,
        "result_package": summary.get("result_package", ""),
        "result_package_validation_passed": bool(validation.get("passed", False)),
        "bdf_validation_passed": bool(bdf.get("passed", False)),
        "missing_property_count": int(bdf.get("missing_property_count", 0)),
        "missing_material_count": int(bdf.get("missing_material_count", 0)),
        "missing_nodes_count": int(bdf.get("missing_nodes_count", 0)),
        "native_ctetra_count": int(native.get("solid_tetra", {}).get("created_count", 0)),
        "native_cbush_count": int(native.get("connectors", {}).get("created_count", 0)),
        "native_conm2_count": int(native.get("masses", {}).get("created_count", 0)),
        "expected_solid_count": expected["solid"],
        "expected_connector_count": expected["connector"],
        "expected_mass_count": expected["mass"],
        "solver_deck_element_fallback_enabled": bool(deck.get("element_creation_enabled", True)),
        "batch_mesh_session_count": int(batch_sessions.get("session_count", 0)),
        "write_statistics_status_counts": final_quality.get("status_counts", {}),
        "quality_summary_passed": bool(final_quality.get("passed", False)),
        "quality_issue_record_count": int(final_quality.get("issue_record_count", 0)),
        "quality_threshold_violation_count": quality_threshold_violation_count(final_quality),
        "quality_numeric_metrics": quality_numeric_metrics(final_quality),
        "bdf_traceability_passed": bool(traceability.get("passed", False)),
        "bdf_traceability_failure_count": int(traceability.get("failure_count", 0)) if traceability else 0,
        "bdf_traceability_mapped_part_count": int(traceability.get("mapped_part_uid_count", 0)) if traceability else 0,
        "quality_repair_loop_status": quality_loop.get("status", ""),
        "quality_repair_loop_iteration_count": int(quality_loop.get("iteration_count", 0)),
        "runtime_seconds": round(float(runtime_seconds), 3),
        "failure_reason": failure_reason,
    }
    result["accepted"] = sample_passed(result)
    if not result["accepted"] and not result["failure_reason"]:
        result["failure_reason"] = "; ".join(sample_failure_reasons(result))
    return result


def failed_sample_result(sample_id: str, result_zip: Path, runtime_seconds: float, failure_reason: str) -> dict[str, Any]:
    return {
        "sample_id": sample_id,
        "ansa_success": False,
        "result_package": str(result_zip),
        "result_package_validation_passed": False,
        "bdf_validation_passed": False,
        "missing_property_count": 0,
        "missing_material_count": 0,
        "missing_nodes_count": 0,
        "native_ctetra_count": 0,
        "native_cbush_count": 0,
        "native_conm2_count": 0,
        "expected_solid_count": 0,
        "expected_connector_count": 0,
        "expected_mass_count": 0,
        "solver_deck_element_fallback_enabled": True,
        "batch_mesh_session_count": 0,
        "write_statistics_status_counts": {},
        "quality_summary_passed": False,
        "quality_issue_record_count": 0,
        "quality_threshold_violation_count": 0,
        "quality_numeric_metrics": [],
        "bdf_traceability_passed": False,
        "bdf_traceability_failure_count": 0,
        "bdf_traceability_mapped_part_count": 0,
        "quality_repair_loop_status": "",
        "quality_repair_loop_iteration_count": 0,
        "runtime_seconds": round(float(runtime_seconds), 3),
        "failure_reason": failure_reason,
        "accepted": False,
    }


def expected_counts(recipe_summary: dict[str, Any]) -> dict[str, int]:
    strategies = recipe_summary.get("strategy_counts", {})
    return {
        "solid": int(strategies.get("solid", 0)) + int(strategies.get("solid_tet", 0)),
        "connector": int(recipe_summary.get("connection_count", 0)),
        "mass": int(recipe_summary.get("mass_only_part_count", 0)),
    }


def quality_loop_passed(status: str) -> bool:
    return str(status).strip().lower() in QUALITY_PASS_STATUSES


def final_quality_summary(batch_quality: dict[str, Any], quality_loop: dict[str, Any]) -> dict[str, Any]:
    records = quality_loop.get("records", [])
    if records:
        last = records[-1]
        if isinstance(last, dict) and isinstance(last.get("summary"), dict):
            return last["summary"]
    return batch_quality


def quality_threshold_violation_count(summary: dict[str, Any]) -> int:
    total = 0
    for report in summary.get("parsed_reports", []):
        total += len(report.get("threshold_violations", []))
    for issue in summary.get("issue_records", []):
        total += len(issue.get("threshold_violations", []))
    return total


def quality_numeric_metrics(summary: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = []
    for report in summary.get("parsed_reports", []):
        parsed = report.get("numeric_metrics")
        if parsed:
            metrics.append(parsed)
    return metrics


def sample_failure_reasons(result: dict[str, Any]) -> list[str]:
    reasons = []
    if not result["ansa_success"]:
        reasons.append("ANSA execution failed")
    if not result["result_package_validation_passed"]:
        reasons.append("result package validation failed")
    if not result["bdf_validation_passed"]:
        reasons.append("BDF validation failed")
    for key in ("missing_property_count", "missing_material_count", "missing_nodes_count"):
        if int(result[key]) != 0:
            reasons.append(f"{key}={result[key]}")
    if int(result["native_ctetra_count"]) < int(result["expected_solid_count"]):
        reasons.append("native CTETRA count below expected solid count")
    if int(result["native_cbush_count"]) < int(result["expected_connector_count"]):
        reasons.append("native CBUSH count below expected connector count")
    if int(result["native_conm2_count"]) < int(result["expected_mass_count"]):
        reasons.append("native CONM2 count below expected mass count")
    if bool(result["solver_deck_element_fallback_enabled"]):
        reasons.append("solver-deck element fallback was enabled")
    if not bool(result["quality_summary_passed"]):
        reasons.append("ANSA numeric quality summary did not pass")
    if int(result.get("quality_threshold_violation_count", 0)) > 0:
        reasons.append("ANSA numeric quality thresholds were violated")
    if not bool(result.get("bdf_traceability_passed", False)):
        reasons.append("BDF source part/material/property traceability failed")
    if not quality_loop_passed(str(result["quality_repair_loop_status"])):
        reasons.append("ANSA quality repair loop did not pass")
    return reasons


def sample_passed(result: dict[str, Any]) -> bool:
    return len(sample_failure_reasons(result)) == 0


def summarize_regression(samples: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [sample for sample in samples if sample.get("accepted")]
    failed = [sample for sample in samples if not sample.get("accepted")]
    return {
        "accepted": len(failed) == 0 and len(samples) > 0,
        "sample_count": len(samples),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "total_runtime_seconds": round(sum(float(sample.get("runtime_seconds", 0.0)) for sample in samples), 3),
        "native_ctetra_total": sum(int(sample.get("native_ctetra_count", 0)) for sample in samples),
        "native_cbush_total": sum(int(sample.get("native_cbush_count", 0)) for sample in samples),
        "native_conm2_total": sum(int(sample.get("native_conm2_count", 0)) for sample in samples),
        "expected_solid_total": sum(int(sample.get("expected_solid_count", 0)) for sample in samples),
        "expected_connector_total": sum(int(sample.get("expected_connector_count", 0)) for sample in samples),
        "expected_mass_total": sum(int(sample.get("expected_mass_count", 0)) for sample in samples),
        "failed_samples": [{"sample_id": sample["sample_id"], "reason": sample.get("failure_reason", "")} for sample in failed],
    }


def write_regression_reports(report: dict[str, Any], output_dir: Path | str, root: Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    markdown = render_regression_report(report)
    (output / "ANSA_REGRESSION_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output / "ANSA_REGRESSION_REPORT.md").write_text(markdown, encoding="utf-8")
    (root / "ANSA_REGRESSION_REPORT.md").write_text(markdown, encoding="utf-8")
    update_delivery_documents(report, root)


def render_regression_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# ANSA Regression Report",
        "",
        f"Generated at: {report['generated_at']}",
        f"Dataset: {report['dataset_dir']}",
        f"Model: {report['model_path']}",
        f"Sample count: {summary['sample_count']}",
        f"Passed: {summary['passed_count']}",
        f"Failed: {summary['failed_count']}",
        f"Total runtime seconds: {summary['total_runtime_seconds']}",
        f"Native CTETRA total: {summary['native_ctetra_total']} / expected {summary['expected_solid_total']}",
        f"Native CBUSH total: {summary['native_cbush_total']} / expected {summary['expected_connector_total']}",
        f"Native CONM2 total: {summary['native_conm2_total']} / expected {summary['expected_mass_total']}",
        f"Acceptance: {'ANSA_REGRESSION_ACCEPTED' if summary['accepted'] else 'FAILED'}",
        "",
        "## Sample Results",
        "",
        "| sample_id | accepted | bdf | missing P/M/N | native CTE/CB/CM | expected S/C/M | BMM sessions | quality | threshold violations | runtime s | failure |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for sample in report["samples"]:
        missing = f"{sample['missing_property_count']}/{sample['missing_material_count']}/{sample['missing_nodes_count']}"
        native = f"{sample['native_ctetra_count']}/{sample['native_cbush_count']}/{sample['native_conm2_count']}"
        expected = f"{sample['expected_solid_count']}/{sample['expected_connector_count']}/{sample['expected_mass_count']}"
        failure = str(sample.get("failure_reason", "")).replace("|", "/")
        lines.append(
            "| {sample_id} | {accepted} | {bdf} | {missing} | {native} | {expected} | {sessions} | {quality} | {violations} | {runtime} | {failure} |".format(
                sample_id=sample["sample_id"],
                accepted=sample["accepted"],
                bdf=sample["bdf_validation_passed"],
                missing=missing,
                native=native,
                expected=expected,
                sessions=sample["batch_mesh_session_count"],
                quality=sample["quality_repair_loop_status"],
                violations=sample.get("quality_threshold_violation_count", 0),
                runtime=sample["runtime_seconds"],
                failure=failure,
            )
        )
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            "| sample_id | bdf traceability | mapped parts | failures |",
            "| --- | --- | --- | --- |",
        ]
    )
    for sample in report["samples"]:
        lines.append(
            "| {sample_id} | {passed} | {mapped} | {failures} |".format(
                sample_id=sample["sample_id"],
                passed=sample.get("bdf_traceability_passed", False),
                mapped=sample.get("bdf_traceability_mapped_part_count", 0),
                failures=sample.get("bdf_traceability_failure_count", 0),
            )
        )
    return "\n".join(lines) + "\n"


def render_delivery_section(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            "## ANSA Production Regression",
            f"- Command: `python scripts/run_ansa_regression.py --sample-count {summary['sample_count']}`",
            f"- Regression report: `ANSA_REGRESSION_REPORT.md`",
            f"- Sample count: {summary['sample_count']}",
            f"- Passed samples: {summary['passed_count']}",
            f"- Failed samples: {summary['failed_count']}",
            f"- Native CTETRA total: {summary['native_ctetra_total']} / expected {summary['expected_solid_total']}",
            f"- Native CBUSH total: {summary['native_cbush_total']} / expected {summary['expected_connector_total']}",
            f"- Native CONM2 total: {summary['native_conm2_total']} / expected {summary['expected_mass_total']}",
            f"- Total runtime seconds: {summary['total_runtime_seconds']}",
            f"- Regression acceptance: {'ANSA_REGRESSION_ACCEPTED' if summary['accepted'] else 'FAILED'}",
            "",
        ]
    )


def update_delivery_documents(report: dict[str, Any], root: Path) -> None:
    section = render_delivery_section(report)
    for filename in ("FINAL_DELIVERY_REPORT.md", "IMPLEMENTATION_STATUS.md"):
        path = root / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        content = replace_or_insert_section(content, "## ANSA Production Regression", section, "## Known Limitations")
        content = replace_final_acceptance(content, bool(report["summary"]["accepted"]))
        path.write_text(content, encoding="utf-8")


def replace_or_insert_section(content: str, heading: str, section: str, before_heading: str) -> str:
    lines = content.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is not None:
        end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
        return "\n".join(lines[:start] + section.rstrip().splitlines() + [""] + lines[end:]).rstrip() + "\n"
    before = next((index for index, line in enumerate(lines) if line.strip() == before_heading), len(lines))
    return "\n".join(lines[:before] + section.rstrip().splitlines() + [""] + lines[before:]).rstrip() + "\n"


def replace_final_acceptance(content: str, regression_accepted: bool) -> str:
    lines = content.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "## Final Acceptance Status"), None)
    if start is None:
        return content
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    previous_block = "\n".join(lines[start:end]).upper()
    status = "ANSA_REGRESSION_ACCEPTED" if regression_accepted and "FAILED" not in previous_block else "FAILED"
    return "\n".join(lines[: start + 1] + ["", status, ""] + lines[end:]).rstrip() + "\n"
