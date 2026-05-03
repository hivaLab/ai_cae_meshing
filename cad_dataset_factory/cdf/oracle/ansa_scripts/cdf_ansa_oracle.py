"""ANSA-internal CDF oracle script skeleton.

This script intentionally performs only controlled failure reporting until the
real ANSA API workflow is bound in a later task.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

try:
    from cad_dataset_factory.cdf.oracle.ansa_scripts.cdf_ansa_api_layer import AnsaApiUnavailable, load_ansa_modules
except ModuleNotFoundError:  # pragma: no cover - fallback for direct ANSA script execution contexts
    from cdf_ansa_api_layer import AnsaApiUnavailable, load_ansa_modules  # type: ignore[no-redef]

EXECUTION_REPORT_SCHEMA = "CDF_ANSA_EXECUTION_REPORT_SM_V1"
CONTROLLED_FAILURE_EXIT_CODE = 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CDF ANSA oracle skeleton")
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execution-report", required=True)
    parser.add_argument("--quality-report", required=True)
    parser.add_argument("--batch-mesh-session", required=True)
    parser.add_argument("--quality-profile", required=True)
    parser.add_argument("--solver-deck", required=True)
    parser.add_argument("--save-ansa-database", required=True, choices=["true", "false"])
    return parser.parse_args(argv)


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("manifest must be a JSON object")
    return loaded


def build_controlled_failure_report(
    *,
    sample_id: str,
    runtime_sec: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": EXECUTION_REPORT_SCHEMA,
        "sample_id": sample_id,
        "accepted": False,
        "ansa_version": "unavailable",
        "step_import_success": False,
        "geometry_cleanup_success": False,
        "midsurface_extraction_success": False,
        "feature_matching_success": False,
        "batch_mesh_success": False,
        "solver_export_success": False,
        "runtime_sec": max(0.0, float(runtime_sec)),
        "outputs": {
            "controlled_failure_reason": reason,
        },
    }


def write_execution_report(path: str | Path, report: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    sample_dir = Path(args.sample_dir)
    manifest_path = Path(args.manifest)
    execution_report_path = Path(args.execution_report)
    sample_id = sample_dir.name
    reason = "ansa_api_unavailable"

    try:
        if not sample_dir.is_dir():
            reason = "missing_sample_dir"
        elif not manifest_path.is_file():
            reason = "missing_manifest"
        else:
            _load_manifest(manifest_path)
            load_ansa_modules()
            reason = "real_ansa_workflow_not_implemented"
    except (AnsaApiUnavailable, ModuleNotFoundError):
        reason = "ansa_api_unavailable"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reason = f"input_validation_failed:{type(exc).__name__}"

    report = build_controlled_failure_report(
        sample_id=sample_id,
        runtime_sec=time.monotonic() - started,
        reason=reason,
    )
    write_execution_report(execution_report_path, report)
    return CONTROLLED_FAILURE_EXIT_CODE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
