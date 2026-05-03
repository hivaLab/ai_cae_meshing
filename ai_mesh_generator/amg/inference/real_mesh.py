"""Real AMG checkpoint inference through the ANSA batch script boundary."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.ansa import RetryPolicy, deterministic_retry_manifest
from ai_mesh_generator.amg.dataset import AmgDatasetSample, load_amg_dataset_sample, load_dataset_index
from ai_mesh_generator.amg.model import ACTION_NAMES, AmgGraphModel, ModelDimensions, apply_action_mask, build_graph_batch, project_model_output
from ai_mesh_generator.amg.model.graph_model import FEATURE_TYPES, PART_CLASSES

MANIFEST_SCHEMA = "AMG_MANIFEST_SM_V1"
DEFAULT_ANSA_EXECUTABLE = r"C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat"
DEFAULT_BATCH_SCRIPT = Path("cad_dataset_factory") / "cdf" / "oracle" / "ansa_scripts" / "cdf_ansa_oracle.py"
REAL_MESH_NAME = "ansa_oracle_mesh.bdf"
EXECUTION_REPORT_NAME = "ansa_execution_report.json"
QUALITY_REPORT_NAME = "ansa_quality_report.json"
INFERENCE_REPORT_NAME = "amg_inference_report.json"
SUCCESS_STATUS = "SUCCESS"
PARTIAL_FAILED_STATUS = "PARTIAL_FAILED"
BLOCKED_STATUS = "BLOCKED"


class AmgRealInferenceError(ValueError):
    """Raised when real AMG inference cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class RealInferenceConfig:
    dataset_root: Path
    checkpoint_path: Path
    output_dir: Path
    ansa_executable: Path = Path(DEFAULT_ANSA_EXECUTABLE)
    training_config_path: Path | None = None
    batch_script: Path = DEFAULT_BATCH_SCRIPT
    limit: int = 20
    sample_ids: tuple[str, ...] = ()
    timeout_sec_per_sample: int = 180
    max_retries: int = 2


@dataclass(frozen=True)
class PredictedManifestResult:
    sample_id: str
    status: str
    manifest: dict[str, Any] | None
    report: dict[str, Any]
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RealMeshSampleResult:
    sample_id: str
    status: str
    attempts: int
    sample_output_dir: str
    manifest_path: str | None = None
    execution_report_path: str | None = None
    quality_report_path: str | None = None
    solver_deck_path: str | None = None
    inference_report_path: str | None = None
    failure_manifest_path: str | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RealInferenceResult:
    status: str
    output_dir: str
    summary_path: str
    attempted_count: int
    success_count: int
    failed_count: int
    retry_count: int
    sample_results: tuple[RealMeshSampleResult, ...]
    failure_reason_counts: dict[str, int]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgRealInferenceError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgRealInferenceError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgRealInferenceError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _jsonable(value: Mapping[str, Any], code: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AmgRealInferenceError(code, "document must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise AmgRealInferenceError(code, "document must be a JSON object")
    return normalized


def _schema(name: str) -> dict[str, Any]:
    return _read_json(_repo_root() / "contracts" / f"{name}.schema.json", "schema_read_failed")


def _validate_schema(document: Mapping[str, Any], schema_name: str, code: str) -> dict[str, Any]:
    normalized = _jsonable(document, code)
    errors = sorted(Draft202012Validator(_schema(schema_name)).iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise AmgRealInferenceError(code, f"{schema_name} {location}: {first.message}")
    return normalized


def _accepted_sample_paths(dataset_root: Path) -> dict[str, Path]:
    index = load_dataset_index(dataset_root)
    paths: dict[str, Path] = {}
    for item in index["accepted_samples"]:
        if isinstance(item, str):
            sample_id = item
            sample_dir = dataset_root / "samples" / sample_id
        elif isinstance(item, Mapping):
            sample_id = item.get("sample_id")
            if not isinstance(sample_id, str) or not sample_id:
                raise AmgRealInferenceError("dataset_index_schema_invalid", "accepted sample records require sample_id", dataset_root)
            sample_dir_value = item.get("sample_dir", f"samples/{sample_id}")
            if not isinstance(sample_dir_value, str):
                raise AmgRealInferenceError("dataset_index_schema_invalid", "sample_dir must be a string", dataset_root)
            sample_dir = Path(sample_dir_value)
            sample_dir = sample_dir if sample_dir.is_absolute() else dataset_root / sample_dir
        else:
            raise AmgRealInferenceError("dataset_index_schema_invalid", "accepted sample records must be strings or objects", dataset_root)
        if sample_id in paths:
            raise AmgRealInferenceError("duplicate_sample_id", "accepted sample ids must be unique", dataset_root)
        paths[sample_id] = sample_dir
    return paths


def _split_ids(dataset_root: Path, split: str) -> list[str]:
    split_path = dataset_root / "splits" / f"{split}.txt"
    if not split_path.is_file():
        return []
    return [line.strip() for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def select_inference_samples(
    dataset_root: str | Path,
    *,
    limit: int = 20,
    sample_ids: Sequence[str] | None = None,
) -> list[AmgDatasetSample]:
    """Select explicit samples, non-empty val split samples, or the final held-out records."""

    root = Path(dataset_root)
    accepted = _accepted_sample_paths(root)
    if sample_ids:
        selected_ids = list(sample_ids)
    else:
        val_ids = _split_ids(root, "val")
        selected_ids = val_ids if val_ids else list(accepted)[-limit:]
    if limit <= 0:
        raise AmgRealInferenceError("invalid_limit", "limit must be positive")
    selected_ids = selected_ids[:limit]
    if not selected_ids:
        raise AmgRealInferenceError("empty_inference_selection", "no samples selected for inference", root)
    samples: list[AmgDatasetSample] = []
    for sample_id in selected_ids:
        if sample_id not in accepted:
            raise AmgRealInferenceError("sample_not_accepted", f"sample id is not accepted: {sample_id}", root)
        samples.append(load_amg_dataset_sample(accepted[sample_id]))
    return samples


def load_trained_checkpoint(
    checkpoint_path: str | Path,
    training_config_path: str | Path | None,
    reference_sample: AmgDatasetSample,
) -> AmgGraphModel:
    """Reconstruct the T-704 model and load a checkpoint."""

    checkpoint = Path(checkpoint_path)
    config_path = Path(training_config_path) if training_config_path is not None else checkpoint.parent / "training_config.json"
    config = _read_json(config_path, "training_config_read_failed")
    hidden_dim = int(config.get("hidden_dim", 32))
    batch = build_graph_batch([reference_sample])
    model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=hidden_dim))
    try:
        payload = torch.load(checkpoint, map_location="cpu")
    except OSError as exc:
        raise AmgRealInferenceError("checkpoint_read_failed", f"could not read checkpoint: {checkpoint}", checkpoint) from exc
    if not isinstance(payload, Mapping) or "model_state" not in payload:
        raise AmgRealInferenceError("malformed_checkpoint", "checkpoint must contain model_state", checkpoint)
    model.load_state_dict(payload["model_state"])
    model.eval()
    return model


def _metadata(sample: AmgDatasetSample) -> list[dict[str, Any]]:
    rows = int(sample.graph.arrays["feature_candidate_features"].shape[0])
    raw = sample.graph.arrays.get("feature_candidate_metadata_json")
    if raw is None or raw.shape[0] != rows:
        raise AmgRealInferenceError("malformed_candidate_metadata", "candidate metadata count must match candidate rows", sample.graph.graph_npz_path)
    items: list[dict[str, Any]] = []
    for value in raw:
        try:
            loaded = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise AmgRealInferenceError("malformed_candidate_metadata", "candidate metadata must parse as JSON", sample.graph.graph_npz_path) from exc
        if not isinstance(loaded, dict):
            raise AmgRealInferenceError("malformed_candidate_metadata", "candidate metadata entries must be objects", sample.graph.graph_npz_path)
        items.append(loaded)
    return items


def _signature_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        if "geometry_signature" in value:
            return str(value["geometry_signature"])
        return json.dumps(dict(value), sort_keys=True)
    if value is None:
        return None
    return str(value)


def _matched_manifest_features(sample: AmgDatasetSample, metadata: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    manifest_features = [dict(feature) for feature in sample.manifest.manifest.get("features", []) if isinstance(feature, Mapping)]
    unmatched = list(range(len(manifest_features)))
    matches: list[dict[str, Any]] = []
    for candidate in metadata:
        candidate_type = str(candidate.get("type", ""))
        candidate_role = str(candidate.get("role", ""))
        candidate_signature = _signature_key(candidate.get("geometry_signature"))
        selected: int | None = None
        if candidate_signature is not None:
            signature_matches = [
                index
                for index in unmatched
                if _signature_key(manifest_features[index].get("geometry_signature")) == candidate_signature
                and str(manifest_features[index].get("type")) == candidate_type
            ]
            if len(signature_matches) == 1:
                selected = signature_matches[0]
        if selected is None:
            typed_matches = [
                index
                for index in unmatched
                if str(manifest_features[index].get("type")) == candidate_type
                and str(manifest_features[index].get("role")) == candidate_role
            ]
            if len(typed_matches) == 1:
                selected = typed_matches[0]
        if selected is None and len(metadata) == len(manifest_features) == 1 and str(manifest_features[0].get("type")) == candidate_type:
            selected = 0
        if selected is None:
            raise AmgRealInferenceError("candidate_label_matching_failed", "candidate could not be matched to structural manifest feature", sample.sample_dir)
        unmatched.remove(selected)
        matches.append(manifest_features[selected])
    if unmatched:
        raise AmgRealInferenceError("candidate_label_matching_failed", "manifest features were not matched to candidates", sample.sample_dir)
    return matches


def _prediction_rejection(sample_id: str, code: str, message: str, report: dict[str, Any]) -> PredictedManifestResult:
    report.update({"sample_id": sample_id, "status": "MODEL_REJECTED", "error_code": code, "message": message})
    return PredictedManifestResult(sample_id=sample_id, status="MODEL_REJECTED", manifest=None, report=report, error_code=code, message=message)


def _action_supported(feature_type: str, action: str) -> bool:
    return (feature_type, action) in {
        ("HOLE", "KEEP_REFINED"),
        ("HOLE", "KEEP_WITH_WASHER"),
        ("HOLE", "SUPPRESS"),
        ("SLOT", "KEEP_REFINED"),
        ("SLOT", "SUPPRESS"),
        ("CUTOUT", "KEEP_REFINED"),
        ("BEND", "KEEP_WITH_BEND_ROWS"),
        ("FLANGE", "KEEP_WITH_FLANGE_SIZE"),
    }


def _positive_int(value: float) -> int:
    return max(1, int(round(float(value))))


def _bounded_h(value: float, mesh: Mapping[str, Any]) -> float:
    return min(max(float(value), float(mesh["h_min_mm"])), float(mesh["h_max_mm"]))


def _controls(feature_type: str, action: str, metadata: Mapping[str, Any], h_values: Sequence[float], div_values: Sequence[float], mesh: Mapping[str, Any]) -> dict[str, Any]:
    h0 = _bounded_h(float(h_values[0]), mesh)
    h1 = _bounded_h(float(h_values[1]), mesh) if len(h_values) > 1 else h0
    d0 = _positive_int(float(div_values[0])) if div_values else 1
    d1 = _positive_int(float(div_values[1])) if len(div_values) > 1 else 1
    growth = min(1.25, float(mesh.get("growth_rate_max", 1.25)))
    if feature_type == "HOLE" and action == "KEEP_REFINED":
        return {"edge_target_length_mm": h0, "circumferential_divisions": d0, "radial_growth_rate": growth}
    if feature_type == "HOLE" and action == "KEEP_WITH_WASHER":
        radius = float(metadata.get("radius_mm", metadata.get("size_1_mm", h0) / 2.0))
        rings = d1
        return {
            "edge_target_length_mm": h0,
            "circumferential_divisions": d0,
            "washer_rings": rings,
            "washer_outer_radius_mm": radius + rings * h1,
            "radial_growth_rate": growth,
        }
    if feature_type in {"HOLE", "SLOT"} and action == "SUPPRESS":
        return {"suppression_rule": "amg_model_predicted_suppression"}
    if feature_type == "SLOT" and action == "KEEP_REFINED":
        return {"edge_target_length_mm": h0, "end_arc_divisions": d0, "straight_edge_divisions": d1, "growth_rate": growth}
    if feature_type == "CUTOUT" and action == "KEEP_REFINED":
        return {"edge_target_length_mm": h0, "perimeter_growth_rate": growth}
    if feature_type == "BEND" and action == "KEEP_WITH_BEND_ROWS":
        return {"bend_target_length_mm": h0, "bend_rows": d0, "growth_rate": growth}
    if feature_type == "FLANGE" and action == "KEEP_WITH_FLANGE_SIZE":
        return {"flange_target_length_mm": h0, "min_elements_across_width": d0}
    raise AmgRealInferenceError("unsupported_manifest_action", f"{feature_type} + {action} is not supported")


def build_predicted_amg_manifest(sample: AmgDatasetSample, model: AmgGraphModel) -> PredictedManifestResult:
    """Run one sample through the model and serialize a schema-valid predicted manifest."""

    metadata = _metadata(sample)
    matched_features = _matched_manifest_features(sample, metadata)
    batch = build_graph_batch([sample])
    if not batch.action_mask.any(dim=1).all():
        return _prediction_rejection(sample.sample_id, "empty_action_mask", "at least one candidate has no allowed action", {})
    with torch.no_grad():
        output = model(batch)
        masked_actions = apply_action_mask(output.feature_action_logits, output.action_mask)
        projected = project_model_output(output, sample.manifest.manifest["global_mesh"])

    part_index = int(output.part_class_logits.argmax(dim=-1)[0].item())
    predicted_part_class = PART_CLASSES[part_index]
    expected_part_class = str(sample.manifest.manifest.get("part", {}).get("part_class"))
    report: dict[str, Any] = {
        "schema": "AMG_REAL_INFERENCE_SAMPLE_REPORT_V1",
        "sample_id": sample.sample_id,
        "part_class_logits": output.part_class_logits.detach().cpu().tolist(),
        "feature_type_logits": output.feature_type_logits.detach().cpu().tolist(),
        "feature_action_logits": masked_actions.detach().cpu().tolist(),
        "log_h": output.log_h.detach().cpu().tolist(),
        "division_values": output.division_values.detach().cpu().tolist(),
        "predicted_part_class": predicted_part_class,
        "expected_part_class": expected_part_class,
    }
    if predicted_part_class != expected_part_class:
        return _prediction_rejection(sample.sample_id, "part_class_mismatch", "predicted part class does not match graph/sample contract", report)

    predicted_type_indices = output.feature_type_logits.argmax(dim=-1).detach().cpu().tolist()
    predicted_action_indices = projected.action_logits.argmax(dim=-1).detach().cpu().tolist()
    h_values = projected.h_values_mm.detach().cpu().tolist()
    division_values = projected.division_values.detach().cpu().tolist()
    feature_reports: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for index, (candidate, matched) in enumerate(zip(metadata, matched_features, strict=True)):
        predicted_type = FEATURE_TYPES[int(predicted_type_indices[index])]
        candidate_type = str(candidate.get("type"))
        manifest_type = str(matched.get("type"))
        if predicted_type != candidate_type or predicted_type != manifest_type:
            report["features"] = feature_reports
            return _prediction_rejection(sample.sample_id, "feature_type_mismatch", "predicted feature type conflicts with candidate metadata", report)
        action = ACTION_NAMES[int(predicted_action_indices[index])]
        if not _action_supported(predicted_type, action):
            report["features"] = feature_reports
            return _prediction_rejection(sample.sample_id, "unsupported_manifest_action", f"{predicted_type} + {action} cannot be executed", report)
        controls = _controls(predicted_type, action, candidate, h_values[index], division_values[index], sample.manifest.manifest["global_mesh"])
        feature_id = str(matched.get("feature_id") or candidate.get("candidate_id"))
        role = str(candidate.get("role", matched.get("role", "UNKNOWN")))
        signature = matched.get("geometry_signature") or {"geometry_signature": candidate.get("geometry_signature")}
        records.append(
            {
                "feature_id": feature_id,
                "type": predicted_type,
                "role": role,
                "action": action,
                "geometry_signature": dict(signature) if isinstance(signature, Mapping) else {"geometry_signature": str(signature)},
                "controls": controls,
            }
        )
        feature_reports.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "feature_id": feature_id,
                "predicted_type": predicted_type,
                "predicted_action": action,
                "controls": controls,
            }
        )

    source_manifest = sample.manifest.manifest
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": dict(source_manifest["part"]),
        "global_mesh": dict(source_manifest["global_mesh"]),
        "features": records,
        "entity_matching": dict(source_manifest["entity_matching"]),
    }
    manifest = _validate_schema(manifest, MANIFEST_SCHEMA, "manifest_schema_invalid")
    report["status"] = "PREDICTED"
    report["features"] = feature_reports
    return PredictedManifestResult(sample_id=sample.sample_id, status="PREDICTED", manifest=manifest, report=report)


def _resolve_path(path: str | Path, root: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (root or _repo_root()) / candidate


def _encode_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _build_ansa_command(
    *,
    executable: Path,
    batch_script: Path,
    sample_dir: Path,
    manifest_path: Path,
    execution_report_path: Path,
    quality_report_path: Path,
) -> list[str]:
    payload = {
        "sample_dir": sample_dir.resolve().as_posix(),
        "manifest": manifest_path.resolve().as_posix(),
        "execution_report": execution_report_path.resolve().as_posix(),
        "quality_report": quality_report_path.resolve().as_posix(),
        "batch_mesh_session": "AMG_SHELL_CONST_THICKNESS_V1",
        "quality_profile": "AMG_QA_SHELL_V1",
        "solver_deck": "NASTRAN",
        "save_ansa_database": "true",
    }
    return [
        executable.resolve().as_posix(),
        "-b",
        "-nogui",
        "--confirm-license-agreement",
        "-exec",
        f"load_script:{batch_script.resolve().as_posix()}",
        "-exec",
        "main",
        f"-process_string:{_encode_payload(payload)}",
    ]


def _copy_inputs(sample: AmgDatasetSample, sample_output_dir: Path) -> None:
    cad_source = sample.sample_dir / "cad" / "input.step"
    if not cad_source.is_file():
        raise AmgRealInferenceError("missing_input_step", "sample requires cad/input.step for real ANSA inference", cad_source)
    cad_target = sample_output_dir / "cad" / "input.step"
    cad_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cad_source, cad_target)
    graph_dir = sample_output_dir / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sample.graph.graph_npz_path, graph_dir / "brep_graph.npz")
    shutil.copyfile(sample.graph.graph_schema_path, graph_dir / "graph_schema.json")


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json(path, "report_read_failed")


def _mesh_is_real(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    head = path.read_text(encoding="utf-8", errors="ignore")[:512].lower()
    return "mock" not in head and "placeholder" not in head


def _attempt_verdict(execution: dict[str, Any] | None, quality: dict[str, Any] | None, mesh_path: Path) -> tuple[str, str, str | None]:
    if execution is None:
        return "ANSA_FAILED", "missing_execution_report", None
    if quality is None:
        return "ANSA_FAILED", "missing_quality_report", None
    outputs = execution.get("outputs", {})
    if isinstance(outputs, Mapping) and "controlled_failure_reason" in outputs:
        return "ANSA_FAILED", "controlled_failure_report", None
    if execution.get("ansa_version") in {"unavailable", "mock-ansa"}:
        return "ANSA_FAILED", "non_real_ansa_report", None
    hard_failed = int(quality.get("quality", {}).get("num_hard_failed_elements", 1))
    if execution.get("accepted") is True and quality.get("accepted") is True and hard_failed == 0 and _mesh_is_real(mesh_path):
        return "VALID_MESH", "valid_mesh", None
    if execution.get("step_import_success") and execution.get("midsurface_extraction_success") and execution.get("batch_mesh_success"):
        retry_case = quality.get("quality", {}).get("retry_case", "global_growth_fail")
        return "MESH_QUALITY_FAILED", "quality_not_accepted", str(retry_case)
    return "ANSA_FAILED", "ansa_execution_failed", None


def _archive_attempt(sample_output_dir: Path, attempt_index: int) -> None:
    archive_dir = sample_output_dir / "attempts" / f"attempt_{attempt_index:02d}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        sample_output_dir / "labels" / "amg_manifest.json",
        sample_output_dir / "reports" / EXECUTION_REPORT_NAME,
        sample_output_dir / "reports" / QUALITY_REPORT_NAME,
        sample_output_dir / "meshes" / REAL_MESH_NAME,
    ):
        if path.is_file():
            target = archive_dir / path.parent.name / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _run_ansa_attempt(
    *,
    manifest: Mapping[str, Any],
    sample_output_dir: Path,
    executable: Path,
    batch_script: Path,
    timeout_sec: int,
    attempt_index: int,
) -> dict[str, Any]:
    manifest_path = sample_output_dir / "labels" / "amg_manifest.json"
    execution_path = sample_output_dir / "reports" / EXECUTION_REPORT_NAME
    quality_path = sample_output_dir / "reports" / QUALITY_REPORT_NAME
    mesh_path = sample_output_dir / "meshes" / REAL_MESH_NAME
    _write_json(manifest_path, manifest)
    command = _build_ansa_command(
        executable=executable,
        batch_script=batch_script,
        sample_dir=sample_output_dir,
        manifest_path=manifest_path,
        execution_report_path=execution_path,
        quality_report_path=quality_path,
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_sec, check=False)
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = None
        stdout = exc.stdout if isinstance(exc.stdout, str) else None
        stderr = exc.stderr if isinstance(exc.stderr, str) else None
        execution = _safe_read_json(execution_path)
        quality = _safe_read_json(quality_path)
        _archive_attempt(sample_output_dir, attempt_index)
        return {
            "attempt": attempt_index,
            "status": "ANSA_FAILED",
            "reason": "ansa_timeout",
            "retry_case": None,
            "command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "runtime_sec": time.monotonic() - started,
            "execution": execution,
            "quality": quality,
            "mesh_path": mesh_path.as_posix(),
        }
    execution = _safe_read_json(execution_path)
    quality = _safe_read_json(quality_path)
    status, reason, retry_case = _attempt_verdict(execution, quality, mesh_path)
    _archive_attempt(sample_output_dir, attempt_index)
    return {
        "attempt": attempt_index,
        "status": status,
        "reason": reason,
        "retry_case": retry_case,
        "command": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "runtime_sec": time.monotonic() - started,
        "execution": execution,
        "quality": quality,
        "mesh_path": mesh_path.as_posix(),
    }


def _write_failure_manifest(sample_output_dir: Path, reason: str) -> str:
    manifest = {"schema_version": MANIFEST_SCHEMA, "status": "MESH_FAILED", "reason": reason}
    _validate_schema(manifest, MANIFEST_SCHEMA, "mesh_failed_manifest_invalid")
    path = sample_output_dir / "labels" / "mesh_failed_manifest.json"
    _write_json(path, manifest)
    return path.as_posix()


def _sample_result_from_report(sample_output_dir: Path, report: Mapping[str, Any]) -> RealMeshSampleResult:
    status = str(report["status"])
    attempts = list(report.get("attempts", []))
    failure_manifest = report.get("failure_manifest")
    return RealMeshSampleResult(
        sample_id=str(report["sample_id"]),
        status=status,
        attempts=len(attempts),
        sample_output_dir=sample_output_dir.as_posix(),
        manifest_path=(sample_output_dir / "labels" / "amg_manifest.json").as_posix() if (sample_output_dir / "labels" / "amg_manifest.json").is_file() else None,
        execution_report_path=(sample_output_dir / "reports" / EXECUTION_REPORT_NAME).as_posix() if (sample_output_dir / "reports" / EXECUTION_REPORT_NAME).is_file() else None,
        quality_report_path=(sample_output_dir / "reports" / QUALITY_REPORT_NAME).as_posix() if (sample_output_dir / "reports" / QUALITY_REPORT_NAME).is_file() else None,
        solver_deck_path=(sample_output_dir / "meshes" / REAL_MESH_NAME).as_posix() if (sample_output_dir / "meshes" / REAL_MESH_NAME).is_file() else None,
        inference_report_path=(sample_output_dir / "reports" / INFERENCE_REPORT_NAME).as_posix(),
        failure_manifest_path=str(failure_manifest) if failure_manifest else None,
        error_code=report.get("error_code"),
        message=report.get("message"),
    )


def _run_sample(
    *,
    sample: AmgDatasetSample,
    model: AmgGraphModel,
    config: RealInferenceConfig,
    executable: Path,
    batch_script: Path,
) -> RealMeshSampleResult:
    sample_output_dir = config.output_dir / "samples" / sample.sample_id
    sample_output_dir.mkdir(parents=True, exist_ok=True)
    _copy_inputs(sample, sample_output_dir)
    prediction = build_predicted_amg_manifest(sample, model)
    report = dict(prediction.report)
    report["source_sample_dir"] = sample.sample_dir.as_posix()
    if prediction.status != "PREDICTED" or prediction.manifest is None:
        report["status"] = "MODEL_REJECTED"
        _write_json(sample_output_dir / "reports" / INFERENCE_REPORT_NAME, report)
        return _sample_result_from_report(sample_output_dir, report)

    current_manifest = dict(prediction.manifest)
    attempts: list[dict[str, Any]] = []
    retry_count = 0
    final_status = "MESH_FAILED"
    final_reason = "quality_not_satisfied_after_retry"
    failure_manifest_path: str | None = None
    for attempt_index in range(1, config.max_retries + 2):
        attempt = _run_ansa_attempt(
            manifest=current_manifest,
            sample_output_dir=sample_output_dir,
            executable=executable,
            batch_script=batch_script,
            timeout_sec=config.timeout_sec_per_sample,
            attempt_index=attempt_index,
        )
        attempts.append(attempt)
        if attempt["status"] == "VALID_MESH":
            final_status = "VALID_MESH"
            final_reason = "valid_mesh"
            break
        if attempt["status"] != "MESH_QUALITY_FAILED":
            final_status = "ANSA_FAILED"
            final_reason = str(attempt["reason"])
            break
        if attempt_index > config.max_retries:
            final_status = "MESH_FAILED"
            final_reason = "quality_not_satisfied_after_retry"
            failure_manifest_path = _write_failure_manifest(sample_output_dir, final_reason)
            break
        retry_count += 1
        try:
            current_manifest = deterministic_retry_manifest(current_manifest, str(attempt["retry_case"]), RetryPolicy(max_attempts=config.max_retries))
        except Exception as exc:
            final_status = "MESH_FAILED"
            final_reason = f"retry_failed:{type(exc).__name__}"
            failure_manifest_path = _write_failure_manifest(sample_output_dir, final_reason)
            break

    report.update(
        {
            "status": final_status,
            "attempts": attempts,
            "retry_count": retry_count,
            "error_code": None if final_status == "VALID_MESH" else final_reason,
            "message": None if final_status == "VALID_MESH" else final_reason,
            "failure_manifest": failure_manifest_path,
        }
    )
    _write_json(sample_output_dir / "reports" / INFERENCE_REPORT_NAME, report)
    return _sample_result_from_report(sample_output_dir, report)


def run_real_mesh_inference(config: RealInferenceConfig) -> RealInferenceResult:
    """Run T-704 checkpoint inference and execute predicted manifests through real ANSA."""

    executable = _resolve_path(config.ansa_executable)
    batch_script = _resolve_path(config.batch_script)
    if not executable.is_file():
        raise AmgRealInferenceError("ansa_executable_not_found", f"ANSA executable does not exist: {executable}", executable)
    if not batch_script.is_file():
        raise AmgRealInferenceError("batch_script_not_found", f"ANSA batch script does not exist: {batch_script}", batch_script)
    samples = select_inference_samples(config.dataset_root, limit=config.limit, sample_ids=config.sample_ids)
    model = load_trained_checkpoint(config.checkpoint_path, config.training_config_path, samples[0])
    config.output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        _run_sample(sample=sample, model=model, config=config, executable=executable, batch_script=batch_script)
        for sample in samples
    ]
    success_count = sum(1 for result in results if result.status == "VALID_MESH")
    failure_counts: dict[str, int] = {}
    retry_count = 0
    for result in results:
        if result.status != "VALID_MESH":
            key = result.error_code or result.status
            failure_counts[key] = failure_counts.get(key, 0) + 1
        report = _safe_read_json(Path(result.inference_report_path)) if result.inference_report_path else None
        if report is not None:
            retry_count += int(report.get("retry_count", 0))
    status = SUCCESS_STATUS if success_count == len(results) else PARTIAL_FAILED_STATUS
    summary = {
        "schema": "AMG_REAL_INFERENCE_SUMMARY_V1",
        "status": status,
        "dataset_root": Path(config.dataset_root).as_posix(),
        "checkpoint_path": Path(config.checkpoint_path).as_posix(),
        "output_dir": config.output_dir.as_posix(),
        "attempted_count": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "retry_count": retry_count,
        "failure_reason_counts": failure_counts,
        "sample_results": [result.__dict__ for result in results],
    }
    summary_path = config.output_dir / "inference_summary.json"
    _write_json(summary_path, summary)
    return RealInferenceResult(
        status=status,
        output_dir=config.output_dir.as_posix(),
        summary_path=summary_path.as_posix(),
        attempted_count=len(results),
        success_count=success_count,
        failed_count=len(results) - success_count,
        retry_count=retry_count,
        sample_results=tuple(results),
        failure_reason_counts=failure_counts,
    )


def _default_training_config(checkpoint: Path) -> Path:
    return checkpoint.parent / "training_config.json"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real AMG checkpoint inference through ANSA")
    parser.add_argument("--dataset", default="runs/pilot_cdf_100")
    parser.add_argument("--checkpoint", default="runs/amg_training_real_pilot/checkpoint.pt")
    parser.add_argument("--training-config", default=None)
    parser.add_argument("--out", default="runs/amg_inference_real_pilot")
    parser.add_argument("--ansa-executable", default=os.environ.get("ANSA_EXECUTABLE", DEFAULT_ANSA_EXECUTABLE))
    parser.add_argument("--batch-script", default=DEFAULT_BATCH_SCRIPT.as_posix())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sample-id", dest="sample_ids", action="append", default=[])
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    checkpoint = Path(args.checkpoint)
    training_config = Path(args.training_config) if args.training_config is not None else _default_training_config(checkpoint)
    try:
        result = run_real_mesh_inference(
            RealInferenceConfig(
                dataset_root=Path(args.dataset),
                checkpoint_path=checkpoint,
                training_config_path=training_config,
                output_dir=Path(args.out),
                ansa_executable=Path(args.ansa_executable),
                batch_script=Path(args.batch_script),
                limit=args.limit,
                sample_ids=tuple(args.sample_ids),
                timeout_sec_per_sample=args.timeout_sec,
                max_retries=args.max_retries,
            )
        )
    except AmgRealInferenceError as exc:
        print(json.dumps({"status": BLOCKED_STATUS, "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps({"status": result.status, "summary_path": result.summary_path, "success_count": result.success_count, "failed_count": result.failed_count}, indent=2, sort_keys=True))
    return 0 if result.status == SUCCESS_STATUS else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
