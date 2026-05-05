"""Fail-closed CDF generate/validate orchestration for real pipeline gates."""

from __future__ import annotations

import json
import math
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
from cad_dataset_factory.cdf.cadgen import (
    BentPartSpec,
    FlatPanelFeatureSpec,
    FlatPanelSpec,
    build_bent_part,
    build_flat_panel_part,
    write_bent_part_outputs,
    write_flat_panel_outputs,
)
from cad_dataset_factory.cdf.config import load_cdf_config
from cad_dataset_factory.cdf.dataset import build_sample_acceptance, write_dataset_index, write_sample_directory
from cad_dataset_factory.cdf.domain import (
    EntitySignaturesDocument,
    FeatureEntitySignature,
    FeatureRole,
    FeatureTruthDocument,
    MeshPolicy,
    PartClass,
)
from cad_dataset_factory.cdf.labels import FeatureClearance, build_amg_manifest, build_aux_labels
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
DEFAULT_PROFILE = "flat_hole_pilot_v1"
MIXED_BENCHMARK_PROFILE = "sm_mixed_benchmark_v1"
FAMILY_EXPANSION_PROFILE = "sm_family_expansion_v1"
QUALITY_EXPLORATION_PROFILE = "sm_quality_exploration_v1"
QUALITY_FAMILY_GENERALIZATION_PROFILE = "sm_quality_family_generalization_v1"
PROFILE_CASE_HOLE = "flat_hole"
PROFILE_CASE_SLOT = "flat_slot"
PROFILE_CASE_CUTOUT = "flat_cutout"
PROFILE_CASE_COMBO = "flat_combo"
PROFILE_CASE_SINGLE_FLANGE = "single_flange"
PROFILE_CASE_L_BRACKET = "l_bracket"
PROFILE_CASE_U_CHANNEL = "u_channel"
PROFILE_CASE_HAT_CHANNEL = "hat_channel"
PROFILE_CASE_HOLE_BOLT = "flat_hole_bolt"
PROFILE_CASE_HOLE_MOUNT = "flat_hole_mount"
PROFILE_CASE_HOLE_RELIEF = "flat_hole_relief"
PROFILE_CASE_SLOT_DRAIN = "flat_slot_drain"
PROFILE_CASE_CUTOUT_RELIEF = "flat_cutout_relief"
PROFILE_CASE_DENSE_COMBO = "flat_dense_combo"
FLAT_PROFILE_CASES = {
    PROFILE_CASE_HOLE,
    PROFILE_CASE_SLOT,
    PROFILE_CASE_CUTOUT,
    PROFILE_CASE_COMBO,
    PROFILE_CASE_HOLE_BOLT,
    PROFILE_CASE_HOLE_MOUNT,
    PROFILE_CASE_HOLE_RELIEF,
    PROFILE_CASE_SLOT_DRAIN,
    PROFILE_CASE_CUTOUT_RELIEF,
    PROFILE_CASE_DENSE_COMBO,
}
BENT_PROFILE_CASES = {
    PROFILE_CASE_SINGLE_FLANGE,
    PROFILE_CASE_L_BRACKET,
    PROFILE_CASE_U_CHANNEL,
    PROFILE_CASE_HAT_CHANNEL,
}
MIXED_BENCHMARK_CASE_COUNTS = (
    (PROFILE_CASE_HOLE, 30),
    (PROFILE_CASE_SLOT, 30),
    (PROFILE_CASE_CUTOUT, 30),
    (PROFILE_CASE_COMBO, 30),
    (PROFILE_CASE_L_BRACKET, 30),
)
MIXED_BENCHMARK_REQUIRED_CASES = tuple(case for case, _count in MIXED_BENCHMARK_CASE_COUNTS)
FAMILY_EXPANSION_CASE_COUNTS = (
    (PROFILE_CASE_HOLE, 30),
    (PROFILE_CASE_SLOT, 30),
    (PROFILE_CASE_CUTOUT, 30),
    (PROFILE_CASE_COMBO, 30),
    (PROFILE_CASE_SINGLE_FLANGE, 30),
    (PROFILE_CASE_L_BRACKET, 30),
    (PROFILE_CASE_U_CHANNEL, 30),
    (PROFILE_CASE_HAT_CHANNEL, 30),
)
FAMILY_EXPANSION_REQUIRED_CASES = tuple(case for case, _count in FAMILY_EXPANSION_CASE_COUNTS)
QUALITY_EXPLORATION_CASES = (
    PROFILE_CASE_HOLE,
    PROFILE_CASE_HOLE_BOLT,
    PROFILE_CASE_HOLE_MOUNT,
    PROFILE_CASE_HOLE_RELIEF,
    PROFILE_CASE_SLOT,
    PROFILE_CASE_SLOT_DRAIN,
    PROFILE_CASE_CUTOUT,
    PROFILE_CASE_CUTOUT_RELIEF,
    PROFILE_CASE_COMBO,
    PROFILE_CASE_DENSE_COMBO,
    PROFILE_CASE_SINGLE_FLANGE,
    PROFILE_CASE_L_BRACKET,
    PROFILE_CASE_U_CHANNEL,
    PROFILE_CASE_HAT_CHANNEL,
)
QUALITY_FAMILY_GENERALIZATION_CASES = QUALITY_EXPLORATION_CASES
QUALITY_FAMILY_GENERALIZATION_MIN_COUNT = len(QUALITY_FAMILY_GENERALIZATION_CASES) * 3
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


def _target_cases_for_profile(profile: str, count: int) -> list[str]:
    if profile == DEFAULT_PROFILE:
        return [PROFILE_CASE_HOLE for _ in range(count)]
    if profile == QUALITY_EXPLORATION_PROFILE:
        return [QUALITY_EXPLORATION_CASES[index % len(QUALITY_EXPLORATION_CASES)] for index in range(count)]
    if profile == QUALITY_FAMILY_GENERALIZATION_PROFILE:
        case_count = len(QUALITY_FAMILY_GENERALIZATION_CASES)
        if count < QUALITY_FAMILY_GENERALIZATION_MIN_COUNT or count % case_count != 0:
            raise CdfPipelineError(
                "invalid_profile_count",
                f"{profile} requires count >= {QUALITY_FAMILY_GENERALIZATION_MIN_COUNT} and a multiple of {case_count}",
            )
        return [QUALITY_FAMILY_GENERALIZATION_CASES[index % case_count] for index in range(count)]
    if profile in {MIXED_BENCHMARK_PROFILE, FAMILY_EXPANSION_PROFILE}:
        case_counts = MIXED_BENCHMARK_CASE_COUNTS if profile == MIXED_BENCHMARK_PROFILE else FAMILY_EXPANSION_CASE_COUNTS
        required_count = sum(case_count for _case, case_count in case_counts)
        if count != required_count:
            raise CdfPipelineError(
                "invalid_profile_count",
                f"{profile} requires count={required_count} for the closed benchmark mix",
            )
        cases: list[str] = []
        remaining = {case: case_count for case, case_count in case_counts}
        while any(case_count > 0 for case_count in remaining.values()):
            for case, _case_count in case_counts:
                if remaining[case] > 0:
                    cases.append(case)
                    remaining[case] -= 1
        return cases
    raise CdfPipelineError("unsupported_profile", f"unsupported CDF generation profile: {profile}")


def _write_splits(dataset_root: Path, accepted_samples: list[dict[str, Any]], profile: str = DEFAULT_PROFILE) -> None:
    splits = dataset_root / "splits"
    splits.mkdir(parents=True, exist_ok=True)
    sample_ids = [str(sample["sample_id"]) for sample in accepted_samples]
    if profile == QUALITY_FAMILY_GENERALIZATION_PROFILE and sample_ids:
        split_map = {"train": [], "val": [], "test": []}
        grouped: dict[str, list[str]] = {}
        for sample in accepted_samples:
            profile_case = sample.get("profile_case")
            if not isinstance(profile_case, str):
                raise CdfPipelineError("missing_profile_case", f"{profile} samples require profile_case metadata")
            grouped.setdefault(profile_case, []).append(str(sample["sample_id"]))
        missing_cases = [case for case in QUALITY_FAMILY_GENERALIZATION_CASES if len(grouped.get(case, [])) < 3]
        if missing_cases:
            raise CdfPipelineError("insufficient_profile_case_coverage", f"{profile} split requires >=3 samples per case; missing {missing_cases[0]}")
        for profile_case in QUALITY_FAMILY_GENERALIZATION_CASES:
            ids = grouped[profile_case]
            split_map["train"].extend(ids[:-2])
            split_map["val"].append(ids[-2])
            split_map["test"].append(ids[-1])
    elif profile in {MIXED_BENCHMARK_PROFILE, FAMILY_EXPANSION_PROFILE, QUALITY_EXPLORATION_PROFILE} and sample_ids:
        train_count = int(0.70 * len(sample_ids))
        val_count = int(0.15 * len(sample_ids))
        split_map = {
            "train": sample_ids[:train_count],
            "val": sample_ids[train_count : train_count + val_count],
            "test": sample_ids[train_count + val_count :],
        }
    else:
        split_map = {"train": sample_ids, "val": [], "test": []}
    for split_name in ("train", "val", "test"):
        (splits / f"{split_name}.txt").write_text(
            "".join(f"{sample_id}\n" for sample_id in split_map[split_name]),
            encoding="utf-8",
        )


def _write_dataset_stats(
    dataset_root: Path,
    *,
    status: str,
    requested_count: int,
    accepted_samples: list[dict[str, Any]],
    rejected_samples: list[dict[str, Any]],
    require_ansa: bool,
    seed: int,
    profile: str = DEFAULT_PROFILE,
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
        "profile": profile,
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
    profile: str = DEFAULT_PROFILE,
    reason: str | None = None,
    runtime_sec: float | None = None,
) -> None:
    config_used = dict(config)
    config_used["generation_profile"] = profile
    write_dataset_index(dataset_root, accepted_samples, rejected_samples, config_used)
    _write_rejected_index(dataset_root, rejected_samples)
    _write_dataset_stats(
        dataset_root,
        status=status,
        requested_count=requested_count,
        accepted_samples=accepted_samples,
        rejected_samples=rejected_samples,
        require_ansa=require_ansa,
        seed=seed,
        profile=profile,
        reason=reason,
        runtime_sec=runtime_sec,
    )
    _write_splits(dataset_root, accepted_samples, profile)
    _copy_contracts(dataset_root)


def _blocked_result(
    dataset_root: Path,
    *,
    config: Mapping[str, Any],
    requested_count: int,
    require_ansa: bool,
    seed: int,
    reason: str,
    profile: str = DEFAULT_PROFILE,
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
        profile=profile,
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


def _flat_panel_spec(
    sample_id: str,
    attempt_index: int,
    rng: random.Random,
    profile_case: str,
) -> FlatPanelSpec:
    is_quality_profile_case = profile_case in {
        PROFILE_CASE_HOLE_BOLT,
        PROFILE_CASE_HOLE_MOUNT,
        PROFILE_CASE_HOLE_RELIEF,
        PROFILE_CASE_SLOT_DRAIN,
        PROFILE_CASE_CUTOUT_RELIEF,
        PROFILE_CASE_DENSE_COMBO,
    }
    if is_quality_profile_case:
        width_mm = 130.0 + 7.0 * (attempt_index % 9)
        height_mm = 85.0 + 6.0 * (attempt_index % 7)
        thickness_mm = 0.9 + 0.15 * (attempt_index % 9)
    else:
        width_mm = 150.0 + 5.0 * (attempt_index % 4)
        height_mm = 95.0 + 5.0 * (attempt_index % 3)
        thickness_mm = 1.2
    features: list[FlatPanelFeatureSpec]
    if profile_case == PROFILE_CASE_HOLE:
        radius_mm = 4.0
        margin = 30.0
        center = (
            rng.uniform(margin, width_mm - margin),
            rng.uniform(margin, height_mm - margin),
        )
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_UNKNOWN_0001",
                type="HOLE",
                role=FeatureRole.UNKNOWN,
                center_uv_mm=center,
                radius_mm=radius_mm,
            )
        ]
    elif profile_case == PROFILE_CASE_HOLE_BOLT:
        radius_mm = 3.0 + 0.4 * (attempt_index % 5)
        center = (
            rng.uniform(35.0, width_mm - 35.0),
            rng.uniform(32.0, height_mm - 32.0),
        )
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_BOLT_0001",
                type="HOLE",
                role=FeatureRole.BOLT,
                center_uv_mm=center,
                radius_mm=radius_mm,
            )
        ]
    elif profile_case == PROFILE_CASE_HOLE_MOUNT:
        radius_mm = 4.0 + 0.25 * (attempt_index % 4)
        center = (
            rng.uniform(38.0, width_mm - 38.0),
            rng.uniform(34.0, height_mm - 34.0),
        )
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_MOUNT_0001",
                type="HOLE",
                role=FeatureRole.MOUNT,
                center_uv_mm=center,
                radius_mm=radius_mm,
            )
        ]
    elif profile_case == PROFILE_CASE_HOLE_RELIEF:
        radius_mm = 0.45 + 0.08 * (attempt_index % 4)
        center = (
            rng.uniform(24.0, width_mm - 24.0),
            rng.uniform(22.0, height_mm - 22.0),
        )
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_RELIEF_0001",
                type="HOLE",
                role=FeatureRole.RELIEF,
                center_uv_mm=center,
                radius_mm=radius_mm,
            )
        ]
    elif profile_case == PROFILE_CASE_SLOT:
        features = [
            FlatPanelFeatureSpec(
                feature_id="SLOT_UNKNOWN_0001",
                type="SLOT",
                role=FeatureRole.UNKNOWN,
                center_uv_mm=(width_mm * 0.50, height_mm * 0.50),
                width_mm=8.0,
                length_mm=28.0,
            )
        ]
    elif profile_case == PROFILE_CASE_SLOT_DRAIN:
        features = [
            FlatPanelFeatureSpec(
                feature_id="SLOT_DRAIN_0001",
                type="SLOT",
                role=FeatureRole.DRAIN,
                center_uv_mm=(width_mm * 0.52, height_mm * 0.50),
                width_mm=0.9 + 0.1 * (attempt_index % 3),
                length_mm=8.0 + 1.5 * (attempt_index % 4),
            )
        ]
    elif profile_case == PROFILE_CASE_CUTOUT:
        features = [
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_PASSAGE_0001",
                type="CUTOUT",
                role=FeatureRole.PASSAGE,
                center_uv_mm=(width_mm * 0.50, height_mm * 0.50),
                width_mm=30.0,
                height_mm=18.0,
            )
        ]
    elif profile_case == PROFILE_CASE_CUTOUT_RELIEF:
        side = 3.0 + 0.25 * (attempt_index % 4)
        features = [
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_RELIEF_0001",
                type="CUTOUT",
                role=FeatureRole.RELIEF,
                center_uv_mm=(width_mm * 0.50, height_mm * 0.50),
                width_mm=side,
                height_mm=side,
            )
        ]
    elif profile_case == PROFILE_CASE_COMBO:
        width_mm = 185.0 + 5.0 * (attempt_index % 4)
        height_mm = 105.0 + 5.0 * (attempt_index % 3)
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_UNKNOWN_0001",
                type="HOLE",
                role=FeatureRole.UNKNOWN,
                center_uv_mm=(35.0, height_mm * 0.50),
                radius_mm=4.0,
            ),
            FlatPanelFeatureSpec(
                feature_id="SLOT_UNKNOWN_0001",
                type="SLOT",
                role=FeatureRole.UNKNOWN,
                center_uv_mm=(90.0, height_mm * 0.50),
                width_mm=8.0,
                length_mm=28.0,
            ),
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_PASSAGE_0001",
                type="CUTOUT",
                role=FeatureRole.PASSAGE,
                center_uv_mm=(145.0, height_mm * 0.50),
                width_mm=30.0,
                height_mm=18.0,
            ),
        ]
    elif profile_case == PROFILE_CASE_DENSE_COMBO:
        width_mm = 205.0 + 6.0 * (attempt_index % 6)
        height_mm = 120.0 + 5.0 * (attempt_index % 5)
        thickness_mm = 1.0 + 0.2 * (attempt_index % 6)
        features = [
            FlatPanelFeatureSpec(
                feature_id="HOLE_BOLT_0001",
                type="HOLE",
                role=FeatureRole.BOLT,
                center_uv_mm=(34.0, height_mm * 0.36),
                radius_mm=3.0 + 0.25 * (attempt_index % 4),
            ),
            FlatPanelFeatureSpec(
                feature_id="HOLE_RELIEF_0001",
                type="HOLE",
                role=FeatureRole.RELIEF,
                center_uv_mm=(34.0, height_mm * 0.70),
                radius_mm=0.55,
            ),
            FlatPanelFeatureSpec(
                feature_id="SLOT_DRAIN_0001",
                type="SLOT",
                role=FeatureRole.DRAIN,
                center_uv_mm=(95.0, height_mm * 0.50),
                width_mm=1.0,
                length_mm=10.0 + 1.0 * (attempt_index % 4),
            ),
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_PASSAGE_0001",
                type="CUTOUT",
                role=FeatureRole.PASSAGE,
                center_uv_mm=(155.0, height_mm * 0.50),
                width_mm=24.0 + 2.0 * (attempt_index % 4),
                height_mm=15.0 + 1.5 * (attempt_index % 3),
            ),
        ]
    else:
        raise CdfPipelineError("unsupported_profile_case", f"unsupported flat-panel profile case: {profile_case}", sample_id)
    return FlatPanelSpec(
        sample_id=sample_id,
        part_name=f"SMT_SM_FLAT_PANEL_T120_P{attempt_index:06d}",
        width_mm=width_mm,
        height_mm=height_mm,
        thickness_mm=thickness_mm,
        features=features,
    )


def _candidate_spec(sample_id: str, attempt_index: int, rng: random.Random) -> FlatPanelSpec:
    return _flat_panel_spec(sample_id, attempt_index, rng, PROFILE_CASE_HOLE)


def _bent_part_spec(sample_id: str, attempt_index: int, profile_case: str, *, quality_variant: bool = False) -> BentPartSpec:
    part_classes = {
        PROFILE_CASE_SINGLE_FLANGE: PartClass.SM_SINGLE_FLANGE,
        PROFILE_CASE_L_BRACKET: PartClass.SM_L_BRACKET,
        PROFILE_CASE_U_CHANNEL: PartClass.SM_U_CHANNEL,
        PROFILE_CASE_HAT_CHANNEL: PartClass.SM_HAT_CHANNEL,
    }
    if profile_case not in part_classes:
        raise CdfPipelineError("unsupported_profile_case", f"unsupported bent-part profile case: {profile_case}", sample_id)
    part_class = part_classes[profile_case]
    if part_class == PartClass.SM_SINGLE_FLANGE:
        length_mm = 105.0 + 4.0 * (attempt_index % 4)
        web_width_mm = 62.0 + 3.0 * (attempt_index % 3)
        flange_width_mm = 24.0 + (4.0 if not quality_variant else 2.0 * (attempt_index % 8))
        side_wall_width = None
    elif part_class == PartClass.SM_L_BRACKET:
        length_mm = 125.0 + 5.0 * (attempt_index % 4)
        web_width_mm = 82.0 + 4.0 * (attempt_index % 3)
        flange_width_mm = 32.0 + (8.0 if not quality_variant else 2.5 * (attempt_index % 9))
        side_wall_width = None
    elif part_class == PartClass.SM_U_CHANNEL:
        length_mm = 135.0 + 5.0 * (attempt_index % 4)
        web_width_mm = 92.0 + 4.0 * (attempt_index % 3)
        flange_width_mm = 28.0 + (6.0 if not quality_variant else 2.0 * (attempt_index % 8))
        side_wall_width = None
    elif part_class == PartClass.SM_HAT_CHANNEL:
        length_mm = 145.0 + 5.0 * (attempt_index % 4)
        web_width_mm = 88.0 + 4.0 * (attempt_index % 3)
        flange_width_mm = 34.0 + (8.0 if not quality_variant else 2.0 * (attempt_index % 7))
        side_wall_width = 30.0 + 2.0 * (attempt_index % 6)
    else:
        raise CdfPipelineError("unsupported_profile_case", f"unsupported bent-part profile case: {profile_case}", sample_id)
    return BentPartSpec(
        sample_id=sample_id,
        part_name=f"SMT_{part_class.value}_T120_P{attempt_index:06d}",
        part_class=part_class,
        length_mm=length_mm,
        web_width_mm=web_width_mm,
        flange_width_mm=flange_width_mm,
        thickness_mm=1.2,
        side_wall_width_mm=side_wall_width,
        bend_angle_deg=75.0 + 5.0 * (attempt_index % 10) if quality_variant else 90.0,
        inner_radius_mm=0.9 + 0.15 * (attempt_index % 7) if quality_variant else 1.0,
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


def _feature_clearances_from_truth(feature_truth: FeatureTruthDocument) -> dict[str, FeatureClearance]:
    part_width = float(feature_truth.part.width_mm or 0.0)
    part_height = float(feature_truth.part.height_mm or 0.0)
    clearances: dict[str, FeatureClearance] = {}
    hole_bounds: list[tuple[str, float, float, float]] = []
    for feature in feature_truth.features:
        if getattr(feature, "type", None) != "HOLE":
            continue
        center_uv = getattr(feature, "center_uv_mm", None)
        radius = float(getattr(feature, "radius_mm", 0.0))
        if center_uv is None or radius <= 0 or part_width <= 0 or part_height <= 0:
            continue
        u, v = float(center_uv[0]), float(center_uv[1])
        hole_bounds.append((feature.feature_id, u, v, radius))
    for feature_id, u, v, radius in hole_bounds:
        boundary = min(u - radius, part_width - u - radius, v - radius, part_height - v - radius)
        nearest = float("inf")
        for other_id, other_u, other_v, other_radius in hole_bounds:
            if other_id == feature_id:
                continue
            nearest = min(nearest, math.hypot(u - other_u, v - other_v) - radius - other_radius)
        if math.isinf(nearest):
            nearest = max(part_width, part_height)
        clearances[feature_id] = FeatureClearance(
            clearance_to_boundary_mm=max(0.001, boundary),
            clearance_to_nearest_feature_mm=max(0.001, nearest),
        )
    return clearances


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
    profile_case: str = PROFILE_CASE_HOLE,
    quality_variant: bool = False,
) -> None:
    if profile_case in FLAT_PROFILE_CASES:
        spec = _flat_panel_spec(sample_id, attempt_index, rng, profile_case)
        generated = build_flat_panel_part(spec)
        write_flat_panel_outputs(attempt_dir, generated)
    elif profile_case in BENT_PROFILE_CASES:
        spec = _bent_part_spec(sample_id, attempt_index, profile_case, quality_variant=quality_variant)
        generated = build_bent_part(spec)
        write_bent_part_outputs(attempt_dir, generated)
    else:
        raise CdfPipelineError("unsupported_profile_case", f"unsupported profile case: {profile_case}", sample_id)
    graph = extract_brep_graph_with_candidates(attempt_dir / "cad" / "input.step")
    _write_graph_outputs(attempt_dir, graph)

    matching_report = build_feature_matching_report(sample_id, generated.feature_truth, graph)
    if not matching_report["accepted"]:
        raise CdfPipelineError("feature_truth_matching_failed", "generated truth must match graph candidates", sample_id)
    matches = match_feature_truth_to_candidates(generated.feature_truth, graph)
    entity_signatures = _entity_signatures_from_matches(generated.feature_truth, graph, matches)
    part_width = generated.feature_truth.part.width_mm
    part_height = generated.feature_truth.part.height_mm
    if part_width is None or part_height is None:
        raise CdfPipelineError("missing_part_extents", "generated feature truth must include width_mm and height_mm", sample_id)
    midsurface_area_mm2 = float(part_width) * float(part_height)
    mesh_policy = _mesh_policy(float(part_width), float(part_height), config)
    feature_policy = _feature_policy(config)
    if profile_case in QUALITY_EXPLORATION_CASES:
        feature_policy["allow_small_feature_suppression"] = True
    manifest = build_amg_manifest(
        feature_truth=generated.feature_truth,
        entity_signatures=entity_signatures,
        mesh_policy=mesh_policy,
        feature_policy=feature_policy,
        midsurface_area_mm2=midsurface_area_mm2,
        feature_clearances=_feature_clearances_from_truth(generated.feature_truth),
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


def _promote_accepted_sample(attempt_dir: Path, sample_dir: Path, sample_id: str, *, profile_case: str | None = None) -> dict[str, Any]:
    _require_real_oracle_acceptance(attempt_dir)
    acceptance = _acceptance_document(sample_id, ansa_accepted=True)
    _write_json(attempt_dir / "reports" / "sample_acceptance.json", acceptance)
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    sample_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(attempt_dir.as_posix(), sample_dir.as_posix())
    record = {
        "sample_id": sample_id,
        "sample_dir": f"samples/{sample_id}",
        "manifest": f"samples/{sample_id}/labels/amg_manifest.json",
        "acceptance_report": f"samples/{sample_id}/reports/sample_acceptance.json",
    }
    if profile_case is not None:
        record["profile_case"] = profile_case
    return record


def _blocked_result_with_rejections(
    dataset_root: Path,
    *,
    config: Mapping[str, Any],
    requested_count: int,
    require_ansa: bool,
    seed: int,
    profile: str,
    reason: str,
    rejected_samples: list[dict[str, Any]],
    runtime_sec: float | None = None,
) -> GenerateDatasetResult:
    _write_dataset_documents(
        dataset_root,
        config=config,
        status=BLOCKED,
        requested_count=requested_count,
        accepted_samples=[],
        rejected_samples=rejected_samples,
        require_ansa=require_ansa,
        seed=seed,
        profile=profile,
        reason=reason,
        runtime_sec=runtime_sec,
    )
    return GenerateDatasetResult(
        status=BLOCKED,
        dataset_root=dataset_root,
        requested_count=requested_count,
        accepted_count=0,
        rejected_count=len(rejected_samples),
        exit_code=BLOCKED_EXIT_CODE,
        reason=reason,
        rejected_samples=tuple(rejected_samples),
    )


def _run_mixed_profile_probe_matrix(
    *,
    dataset_root: Path,
    config: Mapping[str, Any],
    ansa_config: AnsaRunnerConfig,
    env: Mapping[str, str] | None,
    seed: int,
    profile: str,
) -> list[dict[str, Any]]:
    rng = random.Random(seed + 700_600)
    rejected: list[dict[str, Any]] = []
    required_cases = FAMILY_EXPANSION_REQUIRED_CASES if profile == FAMILY_EXPANSION_PROFILE else MIXED_BENCHMARK_REQUIRED_CASES
    for case_index, profile_case in enumerate(required_cases, start=1):
        sample_id = f"probe_{profile_case}"
        probe_dir = dataset_root / "work" / "profile_probe" / f"{case_index:02d}_{profile_case}" / sample_id
        if probe_dir.exists():
            shutil.rmtree(probe_dir)
        try:
            _build_candidate_attempt(
                attempt_dir=probe_dir,
                sample_id=sample_id,
                attempt_index=case_index,
                rng=rng,
                config=config,
                profile_case=profile_case,
                quality_variant=False,
            )
            ansa_result = run_ansa_oracle(
                AnsaRunRequest(
                    sample_dir=probe_dir,
                    config=ansa_config,
                    env=dict(env or os.environ),
                ),
                execute=True,
            )
            if ansa_result.status != "COMPLETED":
                raise CdfPipelineError(ansa_result.error_code or "ansa_probe_not_completed", f"ANSA status {ansa_result.status}", sample_id)
            _require_real_oracle_acceptance(probe_dir)
        except (CdfPipelineError, AnsaReportParseError, AnsaRunnerError, OSError, ValueError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            rejected.append(
                {
                    "sample_attempt_id": f"profile_probe_{case_index:02d}",
                    "sample_id": sample_id,
                    "profile_case": profile_case,
                    "stage": "PROFILE_PROBE",
                    "rejection_reason": str(code),
                    "message": str(exc),
                }
            )
    return rejected


def generate_dataset(
    *,
    config_path: str | Path | None,
    out_dir: str | Path,
    count: int,
    seed: int | None = None,
    require_ansa: bool = False,
    env: Mapping[str, str] | None = None,
    profile: str = DEFAULT_PROFILE,
) -> GenerateDatasetResult:
    """Generate a CDF dataset, counting only real ANSA-accepted samples as accepted."""

    started = time.monotonic()
    if count <= 0:
        raise CdfPipelineError("invalid_count", "count must be positive")
    target_cases = _target_cases_for_profile(profile, count)
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
            profile=profile,
        )

    ansa_config = AnsaRunnerConfig.model_validate(config.get("ansa_oracle", {}))
    if profile in {MIXED_BENCHMARK_PROFILE, FAMILY_EXPANSION_PROFILE} and require_ansa:
        probe_rejections = _run_mixed_profile_probe_matrix(
            dataset_root=dataset_root,
            config=config,
            ansa_config=ansa_config,
            env=env,
            seed=resolved_seed,
            profile=profile,
        )
        if probe_rejections:
            return _blocked_result_with_rejections(
                dataset_root,
                config=config,
                requested_count=count,
                require_ansa=require_ansa,
                seed=resolved_seed,
                profile=profile,
                reason="mixed_profile_probe_failed",
                rejected_samples=probe_rejections,
                runtime_sec=time.monotonic() - started,
            )
    validation = config.get("validation", {})
    max_attempts_per_sample = int(validation.get("max_generation_attempts_per_sample", 50)) if isinstance(validation, Mapping) else 50
    max_attempts = max(count, count * max_attempts_per_sample)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    work_root = dataset_root / "work"
    for attempt_index in range(1, max_attempts + 1):
        if len(accepted) >= count:
            break
        profile_case = target_cases[len(accepted)]
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
                profile_case=profile_case,
                quality_variant=profile in {QUALITY_EXPLORATION_PROFILE, QUALITY_FAMILY_GENERALIZATION_PROFILE},
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
            accepted.append(_promote_accepted_sample(attempt_dir, dataset_root / "samples" / sample_id, sample_id, profile_case=profile_case))
        except (CdfPipelineError, AnsaReportParseError, AnsaRunnerError, OSError, ValueError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            rejected.append(
                {
                    "sample_attempt_id": attempt_id,
                    "sample_id": sample_id,
                    "profile_case": profile_case,
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
        profile=profile,
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
