"""Build schema-valid AMG manifests from CDF truth and deterministic rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from pydantic import Field

from cad_dataset_factory.cdf.domain import (
    BendTruth,
    CdfBaseModel,
    CutoutTruth,
    EntitySignaturesDocument,
    FeatureRole,
    FeatureTruthDocument,
    FlangeTruth,
    HoleTruth,
    ManifestFeatureRecord,
    MeshPolicy,
    SlotTruth,
)
from cad_dataset_factory.cdf.labels.amg_rules import (
    bend_rule,
    cutout_rule,
    flange_rule,
    hole_rule,
    slot_rule,
)


class ManifestBuildError(ValueError):
    """Raised when required manifest input is absent or inconsistent."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = f"{code}"
        if feature_id is not None:
            prefix = f"{prefix} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


class FeatureClearance(CdfBaseModel):
    clearance_to_boundary_mm: float = Field(gt=0)
    clearance_to_nearest_feature_mm: float = Field(gt=0)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_manifest_schema() -> dict[str, Any]:
    path = _repo_root() / "contracts" / "AMG_MANIFEST_SM_V1.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_manifest(manifest: dict[str, Any]) -> None:
    validator = Draft202012Validator(_load_manifest_schema())
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ManifestBuildError("manifest_schema_invalid", f"{location}: {first.message}")


def _as_clearance(value: FeatureClearance | Mapping[str, Any]) -> FeatureClearance:
    if isinstance(value, FeatureClearance):
        return value
    return FeatureClearance.model_validate(value)


def _signature_map(entity_signatures: EntitySignaturesDocument) -> dict[str, dict[str, Any]]:
    return {feature.feature_id: feature.signature for feature in entity_signatures.features}


def _require_signature(signatures: Mapping[str, dict[str, Any]], feature_id: str) -> dict[str, Any]:
    try:
        return signatures[feature_id]
    except KeyError as exc:
        raise ManifestBuildError(
            "missing_entity_signature",
            "every truth feature must have a matching entity signature",
            feature_id,
        ) from exc


def _require_clearance(
    feature_id: str,
    feature_clearances: Mapping[str, FeatureClearance | Mapping[str, Any]] | None,
) -> FeatureClearance:
    if feature_clearances is None or feature_id not in feature_clearances:
        raise ManifestBuildError(
            "missing_feature_clearance",
            "BOLT/MOUNT hole manifest generation requires explicit clearance",
            feature_id,
        )
    return _as_clearance(feature_clearances[feature_id])


def _rule_for_feature(
    feature: HoleTruth | SlotTruth | CutoutTruth | BendTruth | FlangeTruth,
    *,
    thickness_mm: float,
    mesh_policy: MeshPolicy,
    feature_policy: Mapping[str, Any] | None,
    midsurface_area_mm2: float | None,
    feature_clearances: Mapping[str, FeatureClearance | Mapping[str, Any]] | None,
) -> dict[str, Any]:
    mesh_data = mesh_policy.model_dump(mode="json")
    policy = dict(feature_policy or {})
    role = feature.role.value

    if isinstance(feature, HoleTruth):
        clearance_kwargs: dict[str, float] = {}
        if feature.role in {FeatureRole.BOLT, FeatureRole.MOUNT}:
            clearance = _require_clearance(feature.feature_id, feature_clearances)
            clearance_kwargs = {
                "clearance_to_boundary_mm": clearance.clearance_to_boundary_mm,
                "clearance_to_nearest_feature_mm": clearance.clearance_to_nearest_feature_mm,
            }
        return hole_rule(
            radius_mm=feature.radius_mm,
            role=role,
            thickness_mm=thickness_mm,
            mesh_policy=mesh_data,
            feature_policy=policy,
            **clearance_kwargs,
        )

    if isinstance(feature, SlotTruth):
        return slot_rule(
            width_mm=feature.width_mm,
            length_mm=feature.length_mm,
            role=role,
            thickness_mm=thickness_mm,
            mesh_policy=mesh_data,
            feature_policy=policy,
        )

    if isinstance(feature, CutoutTruth):
        if midsurface_area_mm2 is None:
            raise ManifestBuildError(
                "missing_midsurface_area",
                "CUTOUT manifest generation requires midsurface_area_mm2",
                feature.feature_id,
            )
        return cutout_rule(
            width_mm=feature.width_mm,
            height_mm=feature.height_mm,
            area_mm2=feature.width_mm * feature.height_mm,
            midsurface_area_mm2=midsurface_area_mm2,
            role=role,
            mesh_policy=mesh_data,
            feature_policy=policy,
        )

    if isinstance(feature, BendTruth):
        return bend_rule(
            inner_radius_mm=feature.inner_radius_mm,
            angle_deg=feature.angle_deg,
            thickness_mm=feature.thickness_mm,
            mesh_policy=mesh_data,
            feature_policy=policy,
        )

    if isinstance(feature, FlangeTruth):
        return flange_rule(
            width_mm=feature.width_mm,
            mesh_policy=mesh_data,
            feature_policy=policy,
        )

    raise ManifestBuildError("unsupported_feature_type", "unsupported feature type", feature.feature_id)


def build_amg_manifest(
    *,
    feature_truth: FeatureTruthDocument,
    entity_signatures: EntitySignaturesDocument,
    mesh_policy: MeshPolicy,
    feature_policy: Mapping[str, Any] | None = None,
    cad_file: str = "cad/input.step",
    midsurface_area_mm2: float | None = None,
    feature_clearances: Mapping[str, FeatureClearance | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if feature_truth.sample_id != entity_signatures.sample_id:
        raise ManifestBuildError(
            "sample_id_mismatch",
            "feature truth and entity signatures must share sample_id",
        )
    if feature_truth.part.part_name != entity_signatures.part_name:
        raise ManifestBuildError(
            "part_name_mismatch",
            "feature truth part name must match entity signatures part name",
        )
    if midsurface_area_mm2 is not None and midsurface_area_mm2 <= 0:
        raise ManifestBuildError("invalid_midsurface_area", "midsurface_area_mm2 must be positive")

    signatures = _signature_map(entity_signatures)
    features: list[dict[str, Any]] = []

    for feature in feature_truth.features:
        rule_result = _rule_for_feature(
            feature,
            thickness_mm=feature_truth.part.thickness_mm,
            mesh_policy=mesh_policy,
            feature_policy=feature_policy,
            midsurface_area_mm2=midsurface_area_mm2,
            feature_clearances=feature_clearances,
        )
        record = ManifestFeatureRecord(
            feature_id=feature.feature_id,
            type=feature.type,
            role=feature.role,
            action=rule_result["action"],
            geometry_signature=_require_signature(signatures, feature.feature_id),
            controls=rule_result["controls"],
        )
        features.append(record.model_dump(mode="json", exclude_none=True))

    manifest = {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": cad_file,
        "unit": "mm",
        "part": {
            "part_name": feature_truth.part.part_name,
            "part_class": feature_truth.part.part_class.value,
            "idealization": "midsurface_shell",
            "thickness_mm": feature_truth.part.thickness_mm,
            "element_type": "quad_dominant_shell",
            "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
        },
        "global_mesh": mesh_policy.model_dump(mode="json"),
        "features": features,
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }
    _validate_manifest(manifest)
    return manifest


def write_amg_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    _validate_manifest(manifest)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
