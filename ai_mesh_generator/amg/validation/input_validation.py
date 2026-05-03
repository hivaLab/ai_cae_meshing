"""AMG input validation and OUT_OF_SCOPE manifest helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

AMG_MANIFEST_SCHEMA_VERSION = "AMG_MANIFEST_SM_V1"
AMG_CONFIG_SCHEMA_VERSION = "AMG_CONFIG_SM_V1"
AMG_FEATURE_OVERRIDES_SCHEMA_VERSION = "AMG_FEATURE_OVERRIDES_SM_V1"


class AmgInputValidationError(ValueError):
    """Raised when AMG inputs are malformed or cannot be validated safely."""

    def __init__(self, code: str, message: str, manifest: dict[str, Any] | None = None) -> None:
        self.code = code
        self.manifest = manifest
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ValidationCheckResult:
    name: str
    passed: bool
    reason: str | None = None
    message: str | None = None
    measured: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AmgInputValidationResult:
    accepted: bool
    input_step: str
    config: dict[str, Any]
    feature_overrides: dict[str, Any] | None
    checks: list[ValidationCheckResult]
    failure_manifest: dict[str, Any] | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgInputValidationError("json_read_failed", f"could not read JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AmgInputValidationError("json_parse_failed", f"could not parse JSON file: {path}") from exc
    if not isinstance(loaded, dict):
        raise AmgInputValidationError("json_document_not_object", f"JSON document must be an object: {path}")
    return loaded


def _json_object(value: str | Path | Mapping[str, Any] | None, *, default_path: Path | None = None) -> dict[str, Any]:
    if value is None:
        if default_path is None:
            raise AmgInputValidationError("missing_json_document", "JSON document is required")
        raw = _read_json(default_path)
    elif isinstance(value, str | Path):
        raw = _read_json(Path(value))
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise AmgInputValidationError("invalid_json_document", "expected a path or mapping")

    try:
        normalized = json.loads(json.dumps(raw, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AmgInputValidationError("non_json_compatible_document", "document must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise AmgInputValidationError("json_document_not_object", "JSON document must be an object")
    return normalized


def _schema_document(schema_name: str) -> dict[str, Any]:
    return _read_json(_repo_root() / "contracts" / f"{schema_name}.schema.json")


def _validate_schema(document: dict[str, Any], schema_name: str, *, code: str) -> None:
    validator = Draft202012Validator(_schema_document(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        manifest = build_out_of_scope_manifest(code)
        raise AmgInputValidationError(code, f"{schema_name} {location}: {first.message}", manifest)


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _validate_schema(manifest, AMG_MANIFEST_SCHEMA_VERSION, code="invalid_out_of_scope_manifest")


def _load_cadquery() -> Any:
    try:
        import cadquery as cq
    except ModuleNotFoundError as exc:
        raise AmgInputValidationError(
            "cadquery_unavailable",
            "CadQuery is required for STEP geometry validation; install the cad optional dependency",
        ) from exc
    return cq


def _import_step(step_path: Path) -> Any:
    cq = _load_cadquery()
    try:
        return cq.importers.importStep(str(step_path)).val()
    except Exception as exc:
        raise AmgInputValidationError(
            "step_import_failed",
            f"failed to import STEP file: {step_path}",
            build_out_of_scope_manifest("step_import_failed"),
        ) from exc


def _shape_bbox_dims(shape: Any) -> tuple[float, float, float]:
    bbox = shape.BoundingBox()
    return (float(bbox.xlen), float(bbox.ylen), float(bbox.zlen))


def _shape_solids(shape: Any) -> list[Any]:
    try:
        solids = list(shape.Solids())
    except Exception:
        solids = []
    if solids:
        return solids
    try:
        if str(shape.ShapeType()).lower() == "solid":
            return [shape]
    except Exception:
        pass
    return []


def build_out_of_scope_manifest(reason: str, message: str | None = None) -> dict[str, Any]:
    """Build a schema-valid AMG_MANIFEST_SM_V1 OUT_OF_SCOPE manifest."""

    _ = message
    return {
        "schema_version": AMG_MANIFEST_SCHEMA_VERSION,
        "status": "OUT_OF_SCOPE",
        "reason": reason,
    }


def write_out_of_scope_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    normalized = _json_object(manifest)
    _validate_manifest(normalized)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _failure_result(
    *,
    input_step: Path,
    config: dict[str, Any],
    feature_overrides: dict[str, Any] | None,
    checks: list[ValidationCheckResult],
    reason: str,
    message: str,
    measured: dict[str, Any] | None = None,
) -> AmgInputValidationResult:
    checks.append(
        ValidationCheckResult(
            name="failure_manifest",
            passed=False,
            reason=reason,
            message=message,
            measured=measured or {},
        )
    )
    return AmgInputValidationResult(
        accepted=False,
        input_step=input_step.as_posix(),
        config=config,
        feature_overrides=feature_overrides,
        checks=checks,
        failure_manifest=build_out_of_scope_manifest(reason, message),
    )


def _single_connected_solid_check(shape: Any) -> tuple[bool, dict[str, Any]]:
    solids = _shape_solids(shape)
    measured: dict[str, Any] = {"body_count": len(solids), "connected_components": len(solids)}
    if len(solids) != 1:
        measured["solid_is_closed"] = False
        return False, measured
    solid = solids[0]
    try:
        measured["solid_is_valid"] = bool(solid.isValid())
    except Exception:
        measured["solid_is_valid"] = True
    measured["solid_is_closed"] = measured["solid_is_valid"]
    return bool(measured["solid_is_closed"]), measured


def _constant_thickness_check(shape: Any, config: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    configured_thickness = float(config["thickness_mm"])
    dims = [value for value in _shape_bbox_dims(shape) if value > 1.0e-9]
    if not dims:
        return False, {"configured_thickness_mm": configured_thickness, "estimated_thickness_mm": 0.0}
    estimated_thickness = min(dims)
    relative_error = abs(configured_thickness - estimated_thickness) / configured_thickness
    measured = {
        "configured_thickness_mm": configured_thickness,
        "estimated_thickness_mm": estimated_thickness,
        "relative_error": relative_error,
    }
    return relative_error <= 0.05, measured


def _midsurface_pairing_check(shape: Any, config: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    thickness = float(config["thickness_mm"])
    dims = sorted((value for value in _shape_bbox_dims(shape) if value > 1.0e-9), reverse=True)
    slender_dimensions = sum(1 for value in dims[:2] if value >= 4.0 * thickness)
    rho_pair = 1.0 if len(dims) >= 3 and slender_dimensions >= 2 else 0.0
    measured = {
        "rho_pair": rho_pair,
        "bbox_dimensions_mm": dims,
    }
    return rho_pair >= 0.90, measured


def validate_amg_inputs(
    *,
    input_step: str | Path,
    amg_config: str | Path | Mapping[str, Any] | None = None,
    feature_overrides: str | Path | Mapping[str, Any] | None = None,
    run_geometry_checks: bool = True,
) -> AmgInputValidationResult:
    """Validate AMG boundary inputs and return an OUT_OF_SCOPE manifest on scope failures."""

    root = _repo_root()
    step_path = Path(input_step)
    config = _json_object(
        amg_config,
        default_path=root / "configs" / "amg_config.default.json",
    )
    _validate_schema(config, AMG_CONFIG_SCHEMA_VERSION, code="invalid_amg_config")

    overrides = None
    if feature_overrides is not None:
        overrides = _json_object(feature_overrides)
        _validate_schema(overrides, AMG_FEATURE_OVERRIDES_SCHEMA_VERSION, code="invalid_feature_overrides")

    checks = [
        ValidationCheckResult(name="amg_config_schema", passed=True),
        ValidationCheckResult(name="feature_overrides_schema", passed=True, measured={"present": overrides is not None}),
    ]

    if not step_path.is_file():
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason="input_step_not_found",
            message=f"input.step does not exist: {step_path}",
        )
    checks.append(ValidationCheckResult(name="input_step_exists", passed=True))

    if step_path.suffix.lower() not in {".step", ".stp"}:
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason="invalid_step_extension",
            message="input STEP file must use .step or .stp extension",
        )
    checks.append(ValidationCheckResult(name="input_step_extension", passed=True))

    if not run_geometry_checks:
        checks.append(ValidationCheckResult(name="geometry_checks_skipped", passed=True))
        return AmgInputValidationResult(
            accepted=True,
            input_step=step_path.as_posix(),
            config=config,
            feature_overrides=overrides,
            checks=checks,
        )

    try:
        shape = _import_step(step_path)
    except AmgInputValidationError as exc:
        if exc.code == "cadquery_unavailable":
            raise
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason=exc.code,
            message=str(exc),
        )
    checks.append(ValidationCheckResult(name="step_import", passed=True))

    passed, measured = _single_connected_solid_check(shape)
    checks.append(
        ValidationCheckResult(
            name="single_connected_solid",
            passed=passed,
            reason=None if passed else "not_single_connected_solid",
            measured=measured,
        )
    )
    if not passed:
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason="not_single_connected_solid",
            message="input STEP must contain exactly one valid connected solid",
            measured=measured,
        )

    passed, measured = _constant_thickness_check(shape, config)
    checks.append(
        ValidationCheckResult(
            name="constant_thickness",
            passed=passed,
            reason=None if passed else "non_constant_thickness",
            measured=measured,
        )
    )
    if not passed:
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason="non_constant_thickness",
            message="estimated thickness does not match configured thickness tolerance",
            measured=measured,
        )

    passed, measured = _midsurface_pairing_check(shape, config)
    checks.append(
        ValidationCheckResult(
            name="midsurface_pairing",
            passed=passed,
            reason=None if passed else "midsurface_pairing_failed",
            measured=measured,
        )
    )
    if not passed:
        return _failure_result(
            input_step=step_path,
            config=config,
            feature_overrides=overrides,
            checks=checks,
            reason="midsurface_pairing_failed",
            message="input STEP does not satisfy the minimum midsurface pairing feasibility path",
            measured=measured,
        )

    return AmgInputValidationResult(
        accepted=True,
        input_step=step_path.as_posix(),
        config=config,
        feature_overrides=overrides,
        checks=checks,
    )
