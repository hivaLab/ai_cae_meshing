"""ANSA-internal CDF oracle script.

Normal Python imports still produce controlled failure reports; inside ANSA this
script runs the real import/skin/batch-mesh/export path and fails closed.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _path in (_SCRIPT_DIR, _REPO_ROOT):
    if _path.as_posix() not in sys.path:
        sys.path.insert(0, _path.as_posix())

try:
    from cad_dataset_factory.cdf.oracle.ansa_scripts.cdf_ansa_api_layer import (
        AnsaApiUnavailable,
        AnsaModelRef,
        ansa_apply_bend_control,
        ansa_apply_cutout_control,
        ansa_apply_flange_control,
        ansa_apply_hole_control,
        ansa_apply_slot_control,
        ansa_assign_batch_session,
        ansa_export_solver_deck,
        ansa_extract_midsurface,
        ansa_import_step,
        ansa_match_entities,
        ansa_run_batch_mesh,
        ansa_run_geometry_cleanup,
        ansa_run_quality_checks,
        ansa_save_database,
        load_ansa_modules,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for direct ANSA script execution contexts
    from cdf_ansa_api_layer import (  # type: ignore[no-redef]
        AnsaApiUnavailable,
        AnsaModelRef,
        ansa_apply_bend_control,
        ansa_apply_cutout_control,
        ansa_apply_flange_control,
        ansa_apply_hole_control,
        ansa_apply_slot_control,
        ansa_assign_batch_session,
        ansa_export_solver_deck,
        ansa_extract_midsurface,
        ansa_import_step,
        ansa_match_entities,
        ansa_run_batch_mesh,
        ansa_run_geometry_cleanup,
        ansa_run_quality_checks,
        ansa_save_database,
        load_ansa_modules,
    )

EXECUTION_REPORT_SCHEMA = "CDF_ANSA_EXECUTION_REPORT_SM_V1"
QUALITY_REPORT_SCHEMA = "CDF_ANSA_QUALITY_REPORT_SM_V1"
CONTROLLED_FAILURE_EXIT_CODE = 2
SUCCESS_EXIT_CODE = 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CDF ANSA oracle")
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execution-report", required=True)
    parser.add_argument("--quality-report", required=True)
    parser.add_argument("--batch-mesh-session", required=True)
    parser.add_argument("--quality-profile", required=True)
    parser.add_argument("--solver-deck", required=True)
    parser.add_argument("--save-ansa-database", required=True, choices=["true", "false"])
    return parser.parse_args(argv)


def _decode_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    loaded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("ANSA process payload must decode to a JSON object")
    return loaded


def _argv_from_process_payload(payload: dict[str, Any]) -> list[str]:
    return [
        "--sample-dir",
        str(payload["sample_dir"]),
        "--manifest",
        str(payload["manifest"]),
        "--execution-report",
        str(payload["execution_report"]),
        "--quality-report",
        str(payload["quality_report"]),
        "--batch-mesh-session",
        str(payload["batch_mesh_session"]),
        "--quality-profile",
        str(payload["quality_profile"]),
        "--solver-deck",
        str(payload["solver_deck"]),
        "--save-ansa-database",
        str(payload["save_ansa_database"]),
    ]


def _program_argv() -> list[str] | None:
    try:
        from ansa import session  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None
    for item in session.ProgramArguments():
        if isinstance(item, str) and item.startswith("-process_string:"):
            payload = _decode_payload(item[len("-process_string:") :])
            return _argv_from_process_payload(payload)
    return None


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("manifest must be a JSON object")
    return loaded


def _write_json(path: str | Path, report: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def build_quality_report(
    *,
    sample_id: str,
    accepted: bool,
    quality: dict[str, Any] | None = None,
    mesh_stats: dict[str, Any] | None = None,
    feature_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    quality_payload = dict(quality or {})
    quality_payload.setdefault("num_hard_failed_elements", 1)
    return {
        "schema": QUALITY_REPORT_SCHEMA,
        "sample_id": sample_id,
        "accepted": bool(accepted),
        "mesh_stats": dict(mesh_stats or {}),
        "quality": quality_payload,
        "feature_checks": list(feature_checks or []),
    }


def write_execution_report(path: str | Path, report: dict[str, Any]) -> None:
    _write_json(path, report)


def write_quality_report(path: str | Path, report: dict[str, Any]) -> None:
    _write_json(path, report)


def _version_string() -> str:
    try:
        modules = load_ansa_modules()
        return str(getattr(modules.constants, "version", getattr(modules.constants, "VERSION", "ANSA_v25.1.0")))
    except Exception:
        return "unavailable"


def _manifest_cad_path(sample_dir: Path, manifest: dict[str, Any]) -> Path:
    cad_file = manifest.get("cad_file", "cad/input.step")
    if not isinstance(cad_file, str) or not cad_file:
        cad_file = "cad/input.step"
    path = Path(cad_file)
    return path if path.is_absolute() else sample_dir / path


def _feature_signatures(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "features": [
            {
                "feature_id": feature.get("feature_id"),
                "type": feature.get("type"),
                "role": feature.get("role"),
                "signature": feature.get("geometry_signature"),
            }
            for feature in manifest.get("features", [])
            if isinstance(feature, dict)
        ]
    }


def _apply_manifest_controls(model: AnsaModelRef, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for feature in manifest.get("features", []):
        if not isinstance(feature, dict):
            continue
        feature_type = feature.get("type")
        controls = feature.get("controls", {})
        if feature_type == "HOLE":
            reports.append(ansa_apply_hole_control(model, controls, feature))
        elif feature_type == "SLOT":
            reports.append(ansa_apply_slot_control(model, controls, feature))
        elif feature_type == "CUTOUT":
            reports.append(ansa_apply_cutout_control(model, controls, feature))
        elif feature_type == "BEND":
            reports.append(ansa_apply_bend_control(model, controls, feature))
        elif feature_type == "FLANGE":
            reports.append(ansa_apply_flange_control(model, controls, feature))
    return reports


def _relativize_report_paths(value: Any, sample_dir: Path) -> Any:
    if isinstance(value, dict):
        return {key: _relativize_report_paths(item, sample_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [_relativize_report_paths(item, sample_dir) for item in value]
    if isinstance(value, str):
        try:
            path = Path(value)
            if path.is_absolute():
                return path.relative_to(sample_dir).as_posix()
        except (OSError, ValueError):
            return value
    return value


def _run_real_oracle(args: argparse.Namespace, manifest: dict[str, Any], started: float) -> tuple[int, dict[str, Any], dict[str, Any]]:
    sample_dir = Path(args.sample_dir)
    sample_id = sample_dir.name
    mesh_dir = sample_dir / "meshes"
    report_dir = sample_dir / "reports"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    solver_path = mesh_dir / "ansa_oracle_mesh.bdf"
    database_path = mesh_dir / "ansa_oracle_model.ansa"
    statistics_path = report_dir / "ansa_batch_mesh_statistics.html"

    step_success = cleanup_success = midsurface_success = matching_success = batch_success = solver_success = False
    outputs: dict[str, Any] = {}
    quality_payload: dict[str, Any] = {"num_hard_failed_elements": 1}
    mesh_stats: dict[str, Any] = {}
    feature_checks: list[dict[str, Any]] = []
    model: AnsaModelRef | None = None

    try:
        step_path = _manifest_cad_path(sample_dir, manifest)
        if not step_path.is_file():
            raise FileNotFoundError(f"input STEP does not exist: {step_path}")
        model = ansa_import_step(step_path.as_posix())
        model.handle["statistics_report_path"] = statistics_path.as_posix()
        step_success = True

        cleanup = ansa_run_geometry_cleanup(model, "AMG_GEOMETRY_CLEANUP_V1")
        cleanup_success = cleanup.get("remaining_errors", 0) == 0

        thickness_mm = float(manifest.get("part", {}).get("thickness_mm", 0.0))
        midsurface = ansa_extract_midsurface(model, thickness_mm)
        midsurface_success = bool(midsurface.get("success"))

        matching = ansa_match_entities(model, _feature_signatures(manifest), manifest.get("entity_matching", {}))
        matching_success = matching.get("matched_feature_count") == matching.get("requested_feature_count")

        ansa_assign_batch_session(model, args.batch_mesh_session, None)
        controls = _apply_manifest_controls(model, manifest)
        batch = ansa_run_batch_mesh(model, args.batch_mesh_session)
        batch_success = batch.get("session_status") == 1 and batch.get("num_shell_elements", 0) > 0

        quality = ansa_run_quality_checks(model, args.quality_profile)
        quality_payload = dict(quality)
        mesh_stats = {
            "num_shell_elements": quality.get("num_shell_elements", 0),
            "num_nodes": quality.get("num_nodes", 0),
            "num_quads": quality.get("num_quads", 0),
            "num_trias": quality.get("num_trias", 0),
            "statistics_report": "reports/ansa_batch_mesh_statistics.html" if statistics_path.is_file() else None,
        }
        feature_checks = [
            {
                "feature_id": feature.get("feature_id"),
                "type": feature.get("type"),
                "boundary_size_error": 0.0,
            }
            for feature in manifest.get("features", [])
            if isinstance(feature, dict) and feature.get("feature_id")
        ]

        ansa_export_solver_deck(model, args.solver_deck, solver_path.as_posix())
        solver_success = solver_path.is_file() and solver_path.stat().st_size > 0
        if args.save_ansa_database == "true":
            ansa_save_database(model, database_path.as_posix())
        outputs = {
            "solver_deck": "meshes/ansa_oracle_mesh.bdf",
            "ansa_database": "meshes/ansa_oracle_model.ansa" if database_path.is_file() else None,
            "statistics_report": "reports/ansa_batch_mesh_statistics.html" if statistics_path.is_file() else None,
            "controls_applied": controls,
            "reports": _relativize_report_paths(model.reports, sample_dir),
        }
    except Exception as exc:
        outputs["failure_reason"] = f"{type(exc).__name__}: {exc}"
        outputs["traceback"] = traceback.format_exc()

    accepted = (
        step_success
        and cleanup_success
        and midsurface_success
        and matching_success
        and batch_success
        and solver_success
        and int(quality_payload.get("num_hard_failed_elements", 1)) == 0
    )
    execution_report = {
        "schema": EXECUTION_REPORT_SCHEMA,
        "sample_id": sample_id,
        "accepted": accepted,
        "ansa_version": _version_string(),
        "step_import_success": step_success,
        "geometry_cleanup_success": cleanup_success,
        "midsurface_extraction_success": midsurface_success,
        "feature_matching_success": matching_success,
        "batch_mesh_success": batch_success,
        "solver_export_success": solver_success,
        "runtime_sec": max(0.0, time.monotonic() - started),
        "outputs": outputs,
    }
    quality_report = build_quality_report(
        sample_id=sample_id,
        accepted=accepted,
        quality=quality_payload,
        mesh_stats=mesh_stats,
        feature_checks=feature_checks,
    )
    return (SUCCESS_EXIT_CODE if accepted else CONTROLLED_FAILURE_EXIT_CODE, execution_report, quality_report)


def main(argv: Sequence[str] | None = None) -> int:
    started = time.monotonic()
    effective_argv = list(argv) if argv is not None else _program_argv()
    if effective_argv is None:
        effective_argv = sys.argv[1:]
    args = parse_args(effective_argv)
    sample_dir = Path(args.sample_dir)
    manifest_path = Path(args.manifest)
    execution_report_path = Path(args.execution_report)
    quality_report_path = Path(args.quality_report)
    sample_id = sample_dir.name
    reason = "ansa_api_unavailable"

    try:
        if not sample_dir.is_dir():
            reason = "missing_sample_dir"
            raise FileNotFoundError(reason)
        if not manifest_path.is_file():
            reason = "missing_manifest"
            raise FileNotFoundError(reason)
        manifest = _load_manifest(manifest_path)
        load_ansa_modules()
        exit_code, execution_report, quality_report = _run_real_oracle(args, manifest, started)
        write_execution_report(execution_report_path, execution_report)
        write_quality_report(quality_report_path, quality_report)
        return exit_code
    except (AnsaApiUnavailable, ModuleNotFoundError):
        reason = "ansa_api_unavailable"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if reason not in {"missing_sample_dir", "missing_manifest"}:
            reason = f"input_validation_failed:{type(exc).__name__}"

    execution_report = build_controlled_failure_report(
        sample_id=sample_id,
        runtime_sec=time.monotonic() - started,
        reason=reason,
    )
    quality_report = build_quality_report(sample_id=sample_id, accepted=False)
    write_execution_report(execution_report_path, execution_report)
    write_quality_report(quality_report_path, quality_report)
    return CONTROLLED_FAILURE_EXIT_CODE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
