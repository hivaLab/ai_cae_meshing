"""Fail-closed CDF generate/validate orchestration for real pipeline gates."""

from __future__ import annotations

import json
import os
import random
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.brep import extract_brep_graph_with_candidates, write_brep_graph, write_graph_schema
from cad_dataset_factory.cdf.cadgen import FlatPanelFeatureSpec, FlatPanelSpec, build_flat_panel_part, write_flat_panel_outputs
from cad_dataset_factory.cdf.config import load_cdf_config
from cad_dataset_factory.cdf.dataset import build_sample_acceptance, write_dataset_index, write_sample_directory
from cad_dataset_factory.cdf.domain import (
    EntitySignaturesDocument,
    FeatureEntitySignature,
    FeatureRole,
    FeatureTruthDocument,
    MeshPolicy,
)
from cad_dataset_factory.cdf.labels import build_amg_manifest, build_aux_labels
from cad_dataset_factory.cdf.labels.sizing import h0_from_midsurface_area, length_bounds_from_h0
from cad_dataset_factory.cdf.oracle import (
    AnsaReportParseError,
    AnsaRunRequest,
    AnsaRunnerConfig,
    AnsaRunnerError,
    parse_ansa_execution_report,
    parse_ansa_quality_report,
    resolve_ansa_executable,
    run_ansa_oracle,
    summarize_ansa_reports,
)
from cad_dataset_factory.cdf.truth import build_feature_matching_report, match_feature_truth_to_candidates

SUCCESS = "SUCCESS"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
VALIDATION_FAILED = "VALIDATION_FAILED"
BLOCKED_EXIT_CODE = 2
FAILED_EXIT_CODE = 1
VALIDATION_FAILED_EXIT_CODE = 3
SUCCESS_EXIT_CODE = 0
REAL_MESH_RELATIVE_PATH = Path("meshes") / "ansa_oracle_mesh.bdf"
REQUIRED_CONTRACTS = (
    "AMG_MANIFEST_SM_V1.schema.json",
    "AMG_BREP_GRAPH_SM_V1.schema.json",
    "CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json",
    "CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json",
)


class CdfPipelineError(ValueError):
    """Raised when the CDF pipeline cannot continue without hiding a failure."""

    def __init__(self, code: str, message: str, sample_id: str | None = None) -> None:
        self.code = code
        self.sample_id = sample_id
        prefix = code if sample_id is None else f"{code} [{sample_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class GenerateDatasetResult:
    status: str
    dataset_root: Path
    requested_count: int
    accepted_count: int
    rejected_count: int
    exit_code: int
    reason: str | None = None
    accepted_samples: tuple[dict[str, Any], ...] = ()
    rejected_samples: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ValidateDatasetResult:
    status: str
    dataset_root: Path
    accepted_count: int
    error_count: int
    exit_code: int
    errors: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CdfPipelineError("json_read_failed", f"could not read {path}") from exc
    except json.JSONDecodeError as exc:
        raise CdfPipelineError("json_parse_failed", f"could not parse {path}") from exc
    if not isinstance(loaded, dict):
        raise CdfPipelineError("json_document_not_object", f"{path} must contain a JSON object")
    return loaded


def _validate_schema(document: Mapping[str, Any], schema_name: str, path: Path) -> None:
    schema_path = _repo_root() / "contracts" / f"{schema_name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(dict(document)), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise CdfPipelineError("schema_validation_failed", f"{path}: {schema_name} {location}: {first.message}")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _copy_contracts(dataset_root: Path) -> None:
    source_root = _repo_root() / "contracts"
    target_root = dataset_root / "contracts"
    target_root.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_CONTRACTS:
        source = source_root / filename
        if source.is_file():
            shutil.copyfile(source, target_root / filename)


def _write_splits(dataset_root: Path, accepted_samples: list[dict[str, Any]]) -> None:
    splits = dataset_root / "splits"
    splits.mkdir(parents=True, exist_ok=True)
    sample_ids = [str(sample["sample_id"]) for sample in accepted_samples]
    content = "".join(f"{sample_id}\n" for sample_id in sample_ids)
    for split_name in ("train", "val", "test"):
        (splits / f"{split_name}.txt").write_text(content if split_name == "train" else "", encoding="utf-8")


def _write_dataset_stats(
    dataset_root: Path,
    *,
    status: str,
    requested_count: int,
    accepted_samples: list[dict[str, Any]],
    rejected_samples: list[dict[str, Any]],
    require_ansa: bool,
    seed: int,
    reason: str | None = None,
    runtime_sec: float | None = None,
) -> dict[str, Any]:
    rejection_reason_counts: dict[str, int] = {}
    for rejected in rejected_samples:
        rejection_reason = str(rejected.get("rejection_reason", "unknown"))
        rejection_reason_counts[rejection_reason] = rejection_reason_counts.get(rejection_reason, 0) + 1
    stats = {
        "schema": "CDF_DATASET_STATS_SM_V1",
        "status": status,
        "requested_count": requested_count,
        "accepted_count": len(accepted_samples),
        "rejected_count": len(rejected_samples),
        "attempted_count": len(accepted_samples) + len(rejected_samples),
        "rejection_reason_counts": rejection_reason_counts,
        "require_ansa": require_ansa,
        "seed": seed,
        "reason": reason,
    }
    if runtime_sec is not None:
        stats["runtime_sec"] = round(max(0.0, float(runtime_sec)), 6)
    _write_json(dataset_root / "dataset_stats.json", stats)
    return stats


def _write_rejected_index(dataset_root: Path, rejected_samples: list[dict[str, Any]]) -> None:
    _write_json(
        dataset_root / "rejected" / "rejected_index.json",
        {
            "schema": "CDF_REJECTED_INDEX_SM_V1",
            "num_rejected": len(rejected_samples),
            "rejected_samples": rejected_samples,
        },
    )


def _write_dataset_documents(
    dataset_root: Path,
    *,
    config: Mapping[str, Any],
    status: str,
    requested_count: int,
    accepted_samples: list[dict[str, Any]],
    rejected_samples: list[dict[str, Any]],
    require_ansa: bool,
    seed: int,
    reason: str | None = None,
    runtime_sec: float | None = None,
) -> None:
    write_dataset_index(dataset_root, accepted_samples, rejected_samples, dict(config))
    _write_rejected_index(dataset_root, rejected_samples)
    _write_dataset_stats(
        dataset_root,
        status=status,
        requested_count=requested_count,
        accepted_samples=accepted_samples,
        rejected_samples=rejected_samples,
        require_ansa=require_ansa,
        seed=seed,
        reason=reason,
        runtime_sec=runtime_sec,
    )
    _write_splits(dataset_root, accepted_samples)
    _copy_contracts(dataset_root)


def _blocked_result(
    dataset_root: Path,
    *,
    config: Mapping[str, Any],
    requested_count: int,
    require_ansa: bool,
    seed: int,
    reason: str,
) -> GenerateDatasetResult:
    rejected = [
        {
            "sample_attempt_id": "preflight",
            "stage": "ANSA_PREFLIGHT",
            "rejection_reason": reason,
        }
    ]
    _write_dataset_documents(
        dataset_root,
        config=config,
        status=BLOCKED,
        requested_count=requested_count,
        accepted_samples=[],
        rejected_samples=rejected,
        require_ansa=require_ansa,
        seed=seed,
        reason=reason,
    )
    return GenerateDatasetResult(
        status=BLOCKED,
        dataset_root=dataset_root,
        requested_count=requested_count,
        accepted_count=0,
        rejected_count=len(rejected),
        exit_code=BLOCKED_EXIT_CODE,
        reason=reason,
        rejected_samples=tuple(rejected),
    )


def _check_ansa_precondition(config: Mapping[str, Any], require_ansa: bool, env: Mapping[str, str] | None) -> str | None:
    if not require_ansa:
        return None
    ansa_config = AnsaRunnerConfig.model_validate(config.get("ansa_oracle", {}))
    if not ansa_config.enabled:
        return "ansa_oracle_disabled"
    try:
        executable = resolve_ansa_executable(ansa_config.ansa_executable, env)
    except AnsaRunnerError as exc:
        return exc.code
    if not executable.exists():
        return "ansa_executable_not_found"
    return None


def _mesh_policy(width_mm: float, height_mm: float, config: Mapping[str, Any]) -> MeshPolicy:
    h0_mm = h0_from_midsurface_area(width_mm * height_mm)
    h_min_mm, h_max_mm = length_bounds_from_h0(h0_mm)
    global_rule = config.get("global_mesh_rule", {})
    growth_rate = float(global_rule.get("growth_rate_max", 1.35)) if isinstance(global_rule, Mapping) else 1.35
    return MeshPolicy(h0_mm=h0_mm, h_min_mm=h_min_mm, h_max_mm=h_max_mm, growth_rate_max=growth_rate)


def _feature_policy(config: Mapping[str, Any]) -> dict[str, Any]:
    global_rule = config.get("global_mesh_rule", {})
    policy = dict(global_rule) if isinstance(global_rule, Mapping) else {}
    policy.setdefault("allow_small_feature_suppression", False)
    return policy


def _candidate_spec(sample_id: str, attempt_index: int, rng: random.Random) -> FlatPanelSpec:
    width_mm = 140.0 + 5.0 * (attempt_index % 4)
    height_mm = 90.0 + 5.0 * (attempt_index % 3)
    thickness_mm = 1.2
    radius_mm = 4.0
    margin = 30.0
    center = (
        rng.uniform(margin, width_mm - margin),
        rng.uniform(margin, height_mm - margin),
    )
    return FlatPanelSpec(
        sample_id=sample_id,
        part_name=f"SMT_SM_FLAT_PANEL_T120_P{attempt_index:06d}",
        width_mm=width_mm,
        height_mm=height_mm,
        thickness_mm=thickness_mm,
        features=[
            FlatPanelFeatureSpec(
                feature_id="HOLE_UNKNOWN_0001",
                type="HOLE",
                role=FeatureRole.UNKNOWN,
                center_uv_mm=center,
                radius_mm=radius_mm,
            )
        ],
    )


def _entity_signatures_from_matches(
    feature_truth: FeatureTruthDocument,
    graph: Any,
    matches: list[dict[str, Any]],
) -> EntitySignaturesDocument:
    metadata_by_id = {item["candidate_id"]: item for item in graph.candidate_metadata}
    feature_by_id = {feature.feature_id: feature for feature in feature_truth.features}
    signatures: list[FeatureEntitySignature] = []
    for match in matches:
        feature = feature_by_id[match["feature_id"]]
        metadata = metadata_by_id[match["detected_feature_id"]]
        raw_signature = metadata["geometry_signature"]
        signature = raw_signature if isinstance(raw_signature, dict) else {"geometry_signature": str(raw_signature)}
        signatures.append(
            FeatureEntitySignature(
                feature_id=feature.feature_id,
                type=feature.type,
                role=feature.role,
                signature=signature,
            )
        )
    return EntitySignaturesDocument(
        sample_id=feature_truth.sample_id,
        part_name=feature_truth.part.part_name,
        features=signatures,
    )


def _write_graph_outputs(sample_dir: Path, graph: Any) -> None:
    write_brep_graph(sample_dir / "graph" / "brep_graph.npz", graph)
    write_graph_schema(sample_dir / "graph" / "graph_schema.json", graph)


def _is_controlled_or_unreal_execution(execution: Any) -> bool:
    if execution.ansa_version in {"unavailable", "mock-ansa"}:
        return True
    if "controlled_failure_reason" in execution.outputs:
        return True
    return False


def _looks_placeholder(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return True
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:256].lower()
    except OSError:
        return True
    return "mock" in head or "placeholder" in head


def _require_real_oracle_acceptance(sample_dir: Path) -> None:
    execution_path = sample_dir / "reports" / "ansa_execution_report.json"
    quality_path = sample_dir / "reports" / "ansa_quality_report.json"
    mesh_path = sample_dir / REAL_MESH_RELATIVE_PATH
    if not execution_path.is_file():
        raise CdfPipelineError("missing_ansa_execution_report", "accepted samples require real ANSA execution report", sample_dir.name)
    if not quality_path.is_file():
        raise CdfPipelineError("missing_ansa_quality_report", "accepted samples require real ANSA quality report", sample_dir.name)
    if _looks_placeholder(mesh_path):
        raise CdfPipelineError("missing_or_placeholder_oracle_mesh", "accepted samples require a non-placeholder oracle mesh", sample_dir.name)

    execution = parse_ansa_execution_report(execution_path)
    quality = parse_ansa_quality_report(quality_path)
    summary = summarize_ansa_reports(execution, quality)
    if _is_controlled_or_unreal_execution(execution):
        raise CdfPipelineError("unreal_ansa_execution_report", "controlled or mock ANSA reports cannot accept samples", sample_dir.name)
    if not summary.accepted:
        raise CdfPipelineError("ansa_oracle_not_accepted", "ANSA execution and quality reports must both be accepted", sample_dir.name)
    if quality.num_hard_failed_elements != 0:
        raise CdfPipelineError("hard_failed_elements", "accepted samples require zero hard failed elements", sample_dir.name)


def _acceptance_document(sample_id: str, *, ansa_accepted: bool, rejection_reason: str | None = None) -> dict[str, Any]:
    return build_sample_acceptance(
        sample_id,
        {
            "geometry_validation": True,
            "feature_matching": True,
            "manifest_schema": True,
            "ansa_oracle": ansa_accepted,
        },
        rejection_reason=rejection_reason,
    )


def _build_candidate_attempt(
    *,
    attempt_dir: Path,
    sample_id: str,
    attempt_index: int,
    rng: random.Random,
    config: Mapping[str, Any],
) -> None:
    spec = _candidate_spec(sample_id, attempt_index, rng)
    generated = build_flat_panel_part(spec)
    write_flat_panel_outputs(attempt_dir, generated)
    graph = extract_brep_graph_with_candidates(attempt_dir / "cad" / "input.step")
    _write_graph_outputs(attempt_dir, graph)

    matching_report = build_feature_matching_report(sample_id, generated.feature_truth, graph)
    if not matching_report["accepted"]:
        raise CdfPipelineError("feature_truth_matching_failed", "generated truth must match graph candidates", sample_id)
    matches = match_feature_truth_to_candidates(generated.feature_truth, graph)
    entity_signatures = _entity_signatures_from_matches(generated.feature_truth, graph, matches)
    mesh_policy = _mesh_policy(float(spec.width_mm), float(spec.height_mm), config)
    manifest = build_amg_manifest(
        feature_truth=generated.feature_truth,
        entity_signatures=entity_signatures,
        mesh_policy=mesh_policy,
        feature_policy=_feature_policy(config),
        midsurface_area_mm2=float(spec.width_mm) * float(spec.height_mm),
    )
    aux_labels = build_aux_labels(sample_id, manifest, mesh_policy)
    write_sample_directory(
        attempt_dir,
        feature_truth=generated.feature_truth,
        entity_signatures=entity_signatures,
        manifest=manifest,
        aux_labels=aux_labels,
        acceptance=_acceptance_document(sample_id, ansa_accepted=False, rejection_reason="ANSA_ORACLE_PENDING"),
        generator_params=generated.generator_params,
        reports={"feature_matching_report": matching_report},
    )


def _promote_accepted_sample(attempt_dir: Path, sample_dir: Path, sample_id: str) -> dict[str, Any]:
    _require_real_oracle_acceptance(attempt_dir)
    acceptance = _acceptance_document(sample_id, ansa_accepted=True)
    _write_json(attempt_dir / "reports" / "sample_acceptance.json", acceptance)
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    sample_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(attempt_dir.as_posix(), sample_dir.as_posix())
    return {
        "sample_id": sample_id,
        "sample_dir": f"samples/{sample_id}",
        "manifest": f"samples/{sample_id}/labels/amg_manifest.json",
        "acceptance_report": f"samples/{sample_id}/reports/sample_acceptance.json",
    }


def generate_dataset(
    *,
    config_path: str | Path | None,
    out_dir: str | Path,
    count: int,
    seed: int | None = None,
    require_ansa: bool = False,
    env: Mapping[str, str] | None = None,
) -> GenerateDatasetResult:
    """Generate a CDF dataset, counting only real ANSA-accepted samples as accepted."""

    started = time.monotonic()
    if count <= 0:
        raise CdfPipelineError("invalid_count", "count must be positive")
    dataset_root = Path(out_dir)
    dataset_root.mkdir(parents=True, exist_ok=True)
    config = load_cdf_config(config_path)
    resolved_seed = int(seed if seed is not None else config.get("seed", 0))
    rng = random.Random(resolved_seed)
    blocked_reason = _check_ansa_precondition(config, require_ansa, env)
    if blocked_reason is not None:
        return _blocked_result(
            dataset_root,
            config=config,
            requested_count=count,
            require_ansa=require_ansa,
            seed=resolved_seed,
            reason=blocked_reason,
        )

    ansa_config = AnsaRunnerConfig.model_validate(config.get("ansa_oracle", {}))
    validation = config.get("validation", {})
    max_attempts_per_sample = int(validation.get("max_generation_attempts_per_sample", 50)) if isinstance(validation, Mapping) else 50
    max_attempts = max(count, count * max_attempts_per_sample)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    work_root = dataset_root / "work"
    for attempt_index in range(1, max_attempts + 1):
        if len(accepted) >= count:
            break
        sample_id = f"sample_{len(accepted) + 1:06d}"
        attempt_id = f"attempt_{attempt_index:06d}"
        attempt_dir = work_root / attempt_id / sample_id
        if attempt_dir.exists():
            shutil.rmtree(attempt_dir)
        try:
            _build_candidate_attempt(
                attempt_dir=attempt_dir,
                sample_id=sample_id,
                attempt_index=attempt_index,
                rng=rng,
                config=config,
            )
            ansa_result = run_ansa_oracle(
                AnsaRunRequest(
                    sample_dir=attempt_dir,
                    config=ansa_config,
                    env=dict(env or os.environ),
                ),
                execute=require_ansa,
            )
            if ansa_result.status != "COMPLETED":
                raise CdfPipelineError(ansa_result.error_code or "ansa_not_completed", f"ANSA status {ansa_result.status}", sample_id)
            accepted.append(_promote_accepted_sample(attempt_dir, dataset_root / "samples" / sample_id, sample_id))
        except (CdfPipelineError, AnsaReportParseError, AnsaRunnerError, OSError, ValueError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            rejected.append(
                {
                    "sample_attempt_id": attempt_id,
                    "sample_id": sample_id,
                    "stage": "GENERATE",
                    "rejection_reason": str(code),
                    "message": str(exc),
                }
            )

    status = SUCCESS if len(accepted) == count else FAILED
    reason = None if status == SUCCESS else "accepted_count_not_reached"
    _write_dataset_documents(
        dataset_root,
        config=config,
        status=status,
        requested_count=count,
        accepted_samples=accepted,
        rejected_samples=rejected,
        require_ansa=require_ansa,
        seed=resolved_seed,
        reason=reason,
        runtime_sec=time.monotonic() - started,
    )
    return GenerateDatasetResult(
        status=status,
        dataset_root=dataset_root,
        requested_count=count,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        exit_code=SUCCESS_EXIT_CODE if status == SUCCESS else FAILED_EXIT_CODE,
        reason=reason,
        accepted_samples=tuple(accepted),
        rejected_samples=tuple(rejected),
    )


def _dataset_index(dataset_root: Path) -> dict[str, Any]:
    path = dataset_root / "dataset_index.json"
    if not path.is_file():
        raise CdfPipelineError("missing_dataset_index", "dataset_index.json is required")
    index = _read_json(path)
    if index.get("schema") != "CDF_DATASET_INDEX_SM_V1":
        raise CdfPipelineError("malformed_dataset_index", "dataset_index schema must be CDF_DATASET_INDEX_SM_V1")
    return index


def _accepted_records(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = index.get("accepted_samples", [])
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise CdfPipelineError("malformed_dataset_index", "accepted_samples must be a list of objects")
    return [dict(item) for item in records]


def _sample_dir_from_record(dataset_root: Path, record: Mapping[str, Any]) -> Path:
    sample_id = record.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        raise CdfPipelineError("malformed_dataset_index", "accepted sample records require sample_id")
    sample_dir = record.get("sample_dir", f"samples/{sample_id}")
    if not isinstance(sample_dir, str) or not sample_dir:
        raise CdfPipelineError("malformed_dataset_index", "sample_dir must be a string", sample_id)
    return dataset_root / sample_dir


def _validate_sample_acceptance(sample_dir: Path, require_ansa: bool) -> None:
    path = sample_dir / "reports" / "sample_acceptance.json"
    if not path.is_file():
        raise CdfPipelineError("missing_sample_acceptance", "sample_acceptance.json is required", sample_dir.name)
    acceptance = _read_json(path)
    accepted_by = acceptance.get("accepted_by")
    if acceptance.get("accepted") is not True or not isinstance(accepted_by, dict):
        raise CdfPipelineError("sample_not_accepted", "accepted sample record must have accepted=true", sample_dir.name)
    if require_ansa and accepted_by.get("ansa_oracle") is not True:
        raise CdfPipelineError("ansa_oracle_not_accepted", "accepted_by.ansa_oracle must be true", sample_dir.name)


def _validate_manifest_and_graph_contracts(sample_dir: Path) -> None:
    manifest_path = sample_dir / "labels" / "amg_manifest.json"
    graph_schema_path = sample_dir / "graph" / "graph_schema.json"
    graph_npz_path = sample_dir / "graph" / "brep_graph.npz"
    manifest = _read_json(manifest_path)
    graph_schema = _read_json(graph_schema_path)
    _validate_schema(manifest, "AMG_MANIFEST_SM_V1", manifest_path)
    _validate_schema(graph_schema, "AMG_BREP_GRAPH_SM_V1", graph_schema_path)
    try:
        loaded = np.load(graph_npz_path, allow_pickle=False)
    except OSError as exc:
        raise CdfPipelineError("brep_graph_read_failed", "brep_graph.npz must be readable", sample_dir.name) from exc
    required_arrays = {
        "node_type_ids",
        "part_features",
        "face_features",
        "edge_features",
        "coedge_features",
        "vertex_features",
        "feature_candidate_features",
    }
    with loaded:
        missing = sorted(required_arrays.difference(loaded.files))
    if missing:
        raise CdfPipelineError("missing_graph_array", f"missing graph arrays: {', '.join(missing)}", sample_dir.name)


def validate_dataset(
    *,
    dataset_root: str | Path,
    require_ansa: bool = False,
) -> ValidateDatasetResult:
    """Validate accepted samples without accepting mocked or placeholder oracle outputs."""

    root = Path(dataset_root)
    errors: list[dict[str, Any]] = []
    try:
        index = _dataset_index(root)
        records = _accepted_records(index)
    except CdfPipelineError as exc:
        return ValidateDatasetResult(
            status=VALIDATION_FAILED,
            dataset_root=root,
            accepted_count=0,
            error_count=1,
            exit_code=VALIDATION_FAILED_EXIT_CODE,
            errors=({"code": exc.code, "message": str(exc)},),
        )

    required_relative = (
        Path("cad/input.step"),
        Path("graph/brep_graph.npz"),
        Path("graph/graph_schema.json"),
        Path("labels/amg_manifest.json"),
        Path("reports/ansa_execution_report.json"),
        Path("reports/ansa_quality_report.json"),
        REAL_MESH_RELATIVE_PATH,
        Path("reports/sample_acceptance.json"),
    )
    for record in records:
        sample_dir = _sample_dir_from_record(root, record)
        sample_id = sample_dir.name
        try:
            if not sample_dir.is_dir():
                raise CdfPipelineError("missing_sample_dir", "sample directory is required", sample_id)
            for relative in required_relative:
                if not (sample_dir / relative).is_file():
                    raise CdfPipelineError("missing_required_sample_file", f"missing {relative.as_posix()}", sample_id)
            _validate_manifest_and_graph_contracts(sample_dir)
            _validate_sample_acceptance(sample_dir, require_ansa)
            if require_ansa:
                _require_real_oracle_acceptance(sample_dir)
        except (CdfPipelineError, AnsaReportParseError) as exc:
            errors.append(
                {
                    "sample_id": sample_id,
                    "code": getattr(exc, "code", type(exc).__name__),
                    "message": str(exc),
                }
            )

    status = SUCCESS if not errors else VALIDATION_FAILED
    return ValidateDatasetResult(
        status=status,
        dataset_root=root,
        accepted_count=len(records),
        error_count=len(errors),
        exit_code=SUCCESS_EXIT_CODE if status == SUCCESS else VALIDATION_FAILED_EXIT_CODE,
        errors=tuple(errors),
    )
