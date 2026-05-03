"""Run AMG manifests through an ANSA adapter boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.ansa.ansa_adapter_interface import (
    AdapterOperation,
    AnsaAdapter,
    AnsaAdapterError,
)

MANIFEST_SCHEMA = "AMG_MANIFEST_SM_V1"
MESH_FAILED_REASON = "quality_not_satisfied_after_retry"


class ManifestRunnerError(ValueError):
    """Raised when an AMG manifest cannot be mapped or run safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    max_bend_rows: int = 6


@dataclass(frozen=True)
class ManifestRunResult:
    status: str
    manifest: dict[str, Any]
    operations: list[AdapterOperation] = field(default_factory=list)
    attempts: int = 0
    quality_report_path: str | None = None
    solver_deck_path: str | None = None
    failure_manifest: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema(name: str) -> dict[str, Any]:
    return json.loads((_repo_root() / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _jsonable_mapping(value: Mapping[str, Any], *, code: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ManifestRunnerError(code, "document must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise ManifestRunnerError(code, "document must be a JSON object")
    return normalized


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _jsonable_mapping(manifest, code="malformed_manifest")
    validator = Draft202012Validator(_schema(MANIFEST_SCHEMA))
    errors = sorted(validator.iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ManifestRunnerError("manifest_schema_invalid", f"{location}: {first.message}")
    if normalized["status"] != "VALID":
        raise ManifestRunnerError("manifest_not_valid", "only VALID AMG manifests can be executed by the adapter runner")
    return normalized


def _feature_set(feature_id: str) -> str:
    return f"FEATURE_SET_{feature_id}"


def _edge_set(feature_id: str) -> str:
    return f"EDGE_SET_{feature_id}"


def _target_length(controls: Mapping[str, Any], feature_id: str) -> float:
    value = controls.get("edge_target_length_mm")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ManifestRunnerError("missing_edge_target_length", "edge_target_length_mm is required", feature_id)
    return float(value)


def _feature_operation(feature: Mapping[str, Any]) -> AdapterOperation:
    feature_id = str(feature["feature_id"])
    feature_type = str(feature["type"])
    action = str(feature["action"])
    controls = dict(feature.get("controls", {}))

    if feature_type in {"HOLE", "SLOT"} and action == "KEEP_REFINED":
        return AdapterOperation("apply_edge_length", (_edge_set(feature_id), _target_length(controls, feature_id)))
    if feature_type == "CUTOUT" and action == "KEEP_REFINED":
        return AdapterOperation("apply_edge_length", (_edge_set(feature_id), _target_length(controls, feature_id)))
    if feature_type == "HOLE" and action == "KEEP_WITH_WASHER":
        return AdapterOperation("apply_hole_washer", (_feature_set(feature_id), controls))
    if feature_type in {"HOLE", "SLOT"} and action == "SUPPRESS":
        return AdapterOperation("fill_hole", (_feature_set(feature_id),))
    if feature_type == "BEND" and action == "KEEP_WITH_BEND_ROWS":
        return AdapterOperation("apply_bend_rows", (_feature_set(feature_id), controls))
    if feature_type == "FLANGE" and action == "KEEP_WITH_FLANGE_SIZE":
        return AdapterOperation("apply_flange_size", (_feature_set(feature_id), controls))

    raise ManifestRunnerError(
        "unsupported_manifest_action",
        f"{feature_type} + {action} has no T-503 adapter mapping",
        feature_id,
    )


def build_manifest_operations(manifest: Mapping[str, Any]) -> list[AdapterOperation]:
    """Build deterministic adapter operations for a schema-valid AMG manifest."""

    normalized = _validate_manifest(manifest)
    part = normalized["part"]
    global_mesh = normalized["global_mesh"]
    operations = [
        AdapterOperation("import_step", (normalized["cad_file"],)),
        AdapterOperation("run_geometry_cleanup"),
        AdapterOperation("extract_midsurface", (part,)),
        AdapterOperation("assign_thickness", (float(part["thickness_mm"]),)),
        AdapterOperation("build_entity_index"),
        AdapterOperation("match_entities"),
        AdapterOperation("create_sets"),
        AdapterOperation("assign_batch_session", (part["batch_session"],)),
    ]
    operations.extend(_feature_operation(feature) for feature in normalized["features"])
    operations.append(AdapterOperation("run_batch_mesh", (global_mesh["quality_profile"],)))
    return operations


def _execute_operation(adapter: AnsaAdapter, operation: AdapterOperation, manifest: dict[str, Any], entity_map: dict[str, Any] | None) -> dict[str, Any] | None:
    if operation.name == "import_step":
        adapter.import_step(*operation.args)
    elif operation.name == "run_geometry_cleanup":
        adapter.run_geometry_cleanup()
    elif operation.name == "extract_midsurface":
        adapter.extract_midsurface(*operation.args)
    elif operation.name == "assign_thickness":
        adapter.assign_thickness(*operation.args)
    elif operation.name == "build_entity_index":
        adapter.build_entity_index()
    elif operation.name == "match_entities":
        return adapter.match_entities(manifest)
    elif operation.name == "create_sets":
        adapter.create_sets(entity_map or {})
    elif operation.name == "assign_batch_session":
        adapter.assign_batch_session(*operation.args)
    elif operation.name == "apply_edge_length":
        adapter.apply_edge_length(*operation.args)
    elif operation.name == "apply_hole_washer":
        adapter.apply_hole_washer(*operation.args)
    elif operation.name == "fill_hole":
        adapter.fill_hole(*operation.args)
    elif operation.name == "apply_bend_rows":
        adapter.apply_bend_rows(*operation.args)
    elif operation.name == "apply_flange_size":
        adapter.apply_flange_size(*operation.args)
    elif operation.name == "run_batch_mesh":
        adapter.run_batch_mesh(*operation.args)
    else:
        raise ManifestRunnerError("unsupported_adapter_operation", f"unknown operation: {operation.name}")
    return entity_map


def _run_once(
    *,
    manifest: dict[str, Any],
    adapter: AnsaAdapter,
    output_dir: Path,
) -> tuple[list[AdapterOperation], Path, Path, bool, str]:
    operations = build_manifest_operations(manifest)
    entity_map: dict[str, Any] | None = None
    for operation in operations:
        entity_map = _execute_operation(adapter, operation, manifest, entity_map)

    quality_report_path = output_dir / "ansa_quality_report.json"
    solver_deck_path = output_dir / "solver_deck.bdf"
    adapter.export_quality_report(quality_report_path.as_posix())
    quality = json.loads(quality_report_path.read_text(encoding="utf-8"))
    accepted = bool(quality.get("accepted"))
    retry_case = str(quality.get("quality", {}).get("retry_case", "global_growth_fail"))
    if accepted:
        adapter.export_solver_deck(manifest["part"]["batch_session"], solver_deck_path.as_posix())
    return operations, quality_report_path, solver_deck_path, accepted, retry_case


def _copy_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(manifest), allow_nan=False))


def build_mesh_failed_manifest(reason: str = MESH_FAILED_REASON) -> dict[str, Any]:
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "MESH_FAILED",
        "reason": reason,
    }
    validator = Draft202012Validator(_schema(MANIFEST_SCHEMA))
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    if errors:
        raise ManifestRunnerError("mesh_failed_manifest_invalid", errors[0].message)
    return manifest


def deterministic_retry_manifest(
    manifest: Mapping[str, Any],
    retry_case: str,
    retry_policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    """Apply one deterministic retry mutation from AMG.md 11.5."""

    policy = retry_policy or RetryPolicy()
    retried = _validate_manifest(manifest)
    h_min = float(retried["global_mesh"]["h_min_mm"])

    if retry_case == "global_growth_fail":
        retried["global_mesh"]["growth_rate_max"] = min(1.20, float(retried["global_mesh"]["growth_rate_max"]))
        return retried

    if retry_case == "hole_perimeter_quality_fail":
        for feature in retried["features"]:
            if feature["type"] == "HOLE" and "edge_target_length_mm" in feature["controls"]:
                current = float(feature["controls"]["edge_target_length_mm"])
                feature["controls"]["edge_target_length_mm"] = max(h_min, 0.75 * current)
        return retried

    if retry_case == "bend_warpage_skew_fail":
        for feature in retried["features"]:
            if feature["type"] == "BEND" and "bend_rows" in feature["controls"]:
                feature["controls"]["bend_rows"] = min(policy.max_bend_rows, int(feature["controls"]["bend_rows"]) + 1)
        return retried

    if retry_case == "flange_narrow_face_fail":
        for feature in retried["features"]:
            if feature["type"] != "FLANGE":
                continue
            for key in ("flange_target_length_mm", "free_edge_target_length_mm"):
                if key in feature["controls"]:
                    current = float(feature["controls"][key])
                    feature["controls"][key] = max(h_min, 0.80 * current)
        return retried

    raise ManifestRunnerError("unsupported_retry_case", f"unsupported retry case: {retry_case}")


def run_manifest_with_adapter(
    manifest: Mapping[str, Any],
    adapter: AnsaAdapter,
    output_dir: str | Path,
    *,
    dry_run: bool = False,
    retry_policy: RetryPolicy | None = None,
) -> ManifestRunResult:
    """Run a VALID AMG manifest through an adapter or return a dry-run operation plan."""

    policy = retry_policy or RetryPolicy()
    current_manifest = _validate_manifest(manifest)
    output_path = Path(output_dir)
    operations = build_manifest_operations(current_manifest)
    if dry_run:
        return ManifestRunResult(status="DRY_RUN", manifest=current_manifest, operations=operations)

    output_path.mkdir(parents=True, exist_ok=True)
    attempts = 0
    try:
        while True:
            attempts += 1
            operations, quality_path, solver_path, accepted, retry_case = _run_once(
                manifest=current_manifest,
                adapter=adapter,
                output_dir=output_path,
            )
            if accepted:
                return ManifestRunResult(
                    status="COMPLETED",
                    manifest=current_manifest,
                    operations=operations,
                    attempts=attempts,
                    quality_report_path=quality_path.as_posix(),
                    solver_deck_path=solver_path.as_posix(),
                )
            if attempts > policy.max_attempts:
                failure_manifest = build_mesh_failed_manifest()
                return ManifestRunResult(
                    status="MESH_FAILED",
                    manifest=current_manifest,
                    operations=operations,
                    attempts=attempts,
                    quality_report_path=quality_path.as_posix(),
                    failure_manifest=failure_manifest,
                    error_code=MESH_FAILED_REASON,
                    message="quality was not accepted after deterministic retry attempts",
                )
            current_manifest = deterministic_retry_manifest(current_manifest, retry_case, policy)
    except AnsaAdapterError as exc:
        return ManifestRunResult(
            status="FAILED",
            manifest=_copy_manifest(current_manifest),
            operations=operations,
            attempts=attempts,
            error_code=exc.code,
            message=str(exc),
        )
