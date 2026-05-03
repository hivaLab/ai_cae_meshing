"""Deterministic CadQuery flat-panel generator for CDF."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field

from cad_dataset_factory.cdf.domain import (
    CdfBaseModel,
    CutoutTruth,
    FeatureRole,
    FeatureTruthDocument,
    FeatureType,
    HoleTruth,
    PartClass,
    PartParams,
    SlotTruth,
)

PATCH_MAIN_ID = "PATCH_MAIN_0001"
AXIS_SOURCE = "flat_panel_reference_normal"


class FlatPanelBuildError(ValueError):
    """Raised when a flat-panel CAD sample cannot be generated safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


class FlatPanelFeatureSpec(CdfBaseModel):
    feature_id: str
    type: FeatureType
    role: FeatureRole
    center_uv_mm: tuple[float, float]
    radius_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    angle_deg: float = 0.0
    corner_radius_mm: float | None = Field(default=None, ge=0)


class FlatPanelSpec(CdfBaseModel):
    sample_id: str
    part_name: str
    part_class: PartClass = PartClass.SM_FLAT_PANEL
    unit: str = "mm"
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    thickness_mm: float = Field(gt=0)
    corner_radius_mm: float | None = Field(default=0.0, ge=0)
    features: list[FlatPanelFeatureSpec] = Field(default_factory=list)


@dataclass(frozen=True)
class GeneratedFlatPanel:
    spec: FlatPanelSpec
    solid_shape: Any
    reference_midsurface_shape: Any
    feature_truth: FeatureTruthDocument
    generator_params: dict[str, Any]


def _load_cadquery() -> Any:
    try:
        import cadquery as cq
    except ModuleNotFoundError as exc:
        raise FlatPanelBuildError(
            "cadquery_unavailable",
            "CadQuery is required for flat-panel CAD build/export; install the cad optional dependency",
        ) from exc
    return cq


def _close_to_zero(value: float | None) -> bool:
    return value is None or math.isclose(value, 0.0, abs_tol=1e-9)


def _require_dimension(value: float | None, name: str) -> float:
    if value is None or value <= 0:
        raise FlatPanelBuildError("missing_panel_dimension", f"{name} must be positive")
    return value


def _feature_bbox(feature: FlatPanelFeatureSpec) -> tuple[float, float, float, float]:
    u, v = feature.center_uv_mm
    if feature.type == FeatureType.HOLE:
        if feature.radius_mm is None:
            raise FlatPanelBuildError("missing_feature_dimension", "HOLE requires radius_mm", feature.feature_id)
        return (u - feature.radius_mm, u + feature.radius_mm, v - feature.radius_mm, v + feature.radius_mm)

    if feature.type == FeatureType.SLOT:
        if feature.width_mm is None or feature.length_mm is None:
            raise FlatPanelBuildError("missing_feature_dimension", "SLOT requires width_mm and length_mm", feature.feature_id)
        if feature.length_mm < feature.width_mm:
            raise FlatPanelBuildError("invalid_slot_dimension", "SLOT length_mm must be >= width_mm", feature.feature_id)
        if not math.isclose(feature.angle_deg, 0.0, abs_tol=1e-9):
            raise FlatPanelBuildError("unsupported_feature_angle", "T-201 supports axis-aligned SLOT only", feature.feature_id)
        return (
            u - feature.length_mm / 2.0,
            u + feature.length_mm / 2.0,
            v - feature.width_mm / 2.0,
            v + feature.width_mm / 2.0,
        )

    if feature.type == FeatureType.CUTOUT:
        if feature.width_mm is None or feature.height_mm is None:
            raise FlatPanelBuildError(
                "missing_feature_dimension",
                "CUTOUT requires width_mm and height_mm",
                feature.feature_id,
            )
        if not math.isclose(feature.angle_deg, 0.0, abs_tol=1e-9):
            raise FlatPanelBuildError("unsupported_feature_angle", "T-201 supports axis-aligned CUTOUT only", feature.feature_id)
        if not _close_to_zero(feature.corner_radius_mm):
            raise FlatPanelBuildError("unsupported_corner_radius", "rounded CUTOUT corners are deferred", feature.feature_id)
        return (
            u - feature.width_mm / 2.0,
            u + feature.width_mm / 2.0,
            v - feature.height_mm / 2.0,
            v + feature.height_mm / 2.0,
        )

    raise FlatPanelBuildError("unsupported_feature_type", "T-201 supports HOLE, SLOT, and CUTOUT only", feature.feature_id)


def _bboxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[1] and a[1] > b[0] and a[2] < b[3] and a[3] > b[2]


def _validate_spec(spec: FlatPanelSpec) -> tuple[float, float]:
    if spec.unit != "mm":
        raise FlatPanelBuildError("unsupported_unit", "T-201 flat panels require unit mm")
    if spec.part_class != PartClass.SM_FLAT_PANEL:
        raise FlatPanelBuildError("unsupported_part_class", "T-201 supports SM_FLAT_PANEL only")
    width = _require_dimension(spec.width_mm, "width_mm")
    height = _require_dimension(spec.height_mm, "height_mm")
    if not _close_to_zero(spec.corner_radius_mm):
        raise FlatPanelBuildError("unsupported_corner_radius", "nonzero flat-panel corner radius is deferred")

    seen_ids: set[str] = set()
    boxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for feature in spec.features:
        if feature.feature_id in seen_ids:
            raise FlatPanelBuildError("duplicate_feature_id", "feature ids must be unique", feature.feature_id)
        seen_ids.add(feature.feature_id)
        bbox = _feature_bbox(feature)
        if bbox[0] < 0 or bbox[1] > width or bbox[2] < 0 or bbox[3] > height:
            raise FlatPanelBuildError("feature_out_of_bounds", "feature must fit inside the flat-panel boundary", feature.feature_id)
        for other_id, other_bbox in boxes:
            if _bboxes_overlap(bbox, other_bbox):
                raise FlatPanelBuildError(
                    "feature_overlap",
                    f"feature bounding box overlaps {other_id}",
                    feature.feature_id,
                )
        boxes.append((feature.feature_id, bbox))

    return width, height


def _truth_for_feature(feature: FlatPanelFeatureSpec) -> HoleTruth | SlotTruth | CutoutTruth:
    if feature.type == FeatureType.HOLE:
        return HoleTruth(
            feature_id=feature.feature_id,
            role=feature.role,
            created_by="cadgen.flat_panel.hole_cut",
            center_uv_mm=feature.center_uv_mm,
            center_mm=(feature.center_uv_mm[0], feature.center_uv_mm[1], 0.0),
            axis=(0.0, 0.0, 1.0),
            radius_mm=feature.radius_mm,
            patch_id=PATCH_MAIN_ID,
            axis_source=AXIS_SOURCE,
        )

    if feature.type == FeatureType.SLOT:
        return SlotTruth(
            feature_id=feature.feature_id,
            role=feature.role,
            created_by="cadgen.flat_panel.slot_cut",
            center_uv_mm=feature.center_uv_mm,
            width_mm=feature.width_mm,
            length_mm=feature.length_mm,
            angle_deg=0.0,
            patch_id=PATCH_MAIN_ID,
            axis_source=AXIS_SOURCE,
        )

    if feature.type == FeatureType.CUTOUT:
        return CutoutTruth(
            feature_id=feature.feature_id,
            role=feature.role,
            created_by="cadgen.flat_panel.cutout_cut",
            center_uv_mm=feature.center_uv_mm,
            width_mm=feature.width_mm,
            height_mm=feature.height_mm,
            corner_radius_mm=0.0,
            angle_deg=0.0,
            patch_id=PATCH_MAIN_ID,
            axis_source=AXIS_SOURCE,
        )

    raise FlatPanelBuildError("unsupported_feature_type", "T-201 supports HOLE, SLOT, and CUTOUT only", feature.feature_id)


def _build_feature_truth(spec: FlatPanelSpec) -> FeatureTruthDocument:
    return FeatureTruthDocument(
        sample_id=spec.sample_id,
        part=PartParams(
            part_name=spec.part_name,
            part_class=PartClass.SM_FLAT_PANEL,
            thickness_mm=spec.thickness_mm,
            width_mm=spec.width_mm,
            height_mm=spec.height_mm,
            corner_radius_mm=0.0,
        ),
        features=[_truth_for_feature(feature) for feature in spec.features],
    )


def _feature_params(feature: FlatPanelFeatureSpec) -> dict[str, Any]:
    data = {
        "feature_id": feature.feature_id,
        "type": feature.type.value,
        "role": feature.role.value,
        "center_uv_mm": list(feature.center_uv_mm),
    }
    for key in ("radius_mm", "width_mm", "height_mm", "length_mm"):
        value = getattr(feature, key)
        if value is not None:
            data[key] = value
    return data


def _generator_params(spec: FlatPanelSpec) -> dict[str, Any]:
    return {
        "schema": "CDF_GENERATOR_PARAMS_SM_V1",
        "sample_id": spec.sample_id,
        "part_class": spec.part_class.value,
        "canonical_part_name": spec.part_name,
        "W_mm": spec.width_mm,
        "H_mm": spec.height_mm,
        "thickness_mm": spec.thickness_mm,
        "corner_radius_mm": 0.0,
        "features": [_feature_params(feature) for feature in spec.features],
    }


def _cutter_for_feature(cq: Any, feature: FlatPanelFeatureSpec, through_depth_mm: float) -> Any:
    u, v = feature.center_uv_mm
    workplane = cq.Workplane("XY").center(u, v)
    if feature.type == FeatureType.HOLE:
        return workplane.circle(feature.radius_mm).extrude(through_depth_mm, both=True)
    if feature.type == FeatureType.SLOT:
        return workplane.slot2D(feature.length_mm, feature.width_mm, 0.0).extrude(through_depth_mm, both=True)
    if feature.type == FeatureType.CUTOUT:
        return workplane.rect(feature.width_mm, feature.height_mm).extrude(through_depth_mm, both=True)
    raise FlatPanelBuildError("unsupported_feature_type", "T-201 supports HOLE, SLOT, and CUTOUT only", feature.feature_id)


def _inner_wire_for_feature(cq: Any, feature: FlatPanelFeatureSpec) -> Any:
    u, v = feature.center_uv_mm
    workplane = cq.Workplane("XY").center(u, v)
    if feature.type == FeatureType.HOLE:
        return workplane.circle(feature.radius_mm).val()
    if feature.type == FeatureType.SLOT:
        return workplane.slot2D(feature.length_mm, feature.width_mm, 0.0).val()
    if feature.type == FeatureType.CUTOUT:
        return workplane.rect(feature.width_mm, feature.height_mm).val()
    raise FlatPanelBuildError("unsupported_feature_type", "T-201 supports HOLE, SLOT, and CUTOUT only", feature.feature_id)


def build_flat_panel_part(spec: FlatPanelSpec) -> GeneratedFlatPanel:
    """Build a flat-panel solid, reference midsurface, and feature truth."""

    width, height = _validate_spec(spec)
    feature_truth = _build_feature_truth(spec)
    generator_params = _generator_params(spec)

    cq = _load_cadquery()
    solid = cq.Workplane("XY").box(width, height, spec.thickness_mm, centered=(False, False, True))
    through_depth = spec.thickness_mm * 3.0
    for feature in spec.features:
        solid = solid.cut(_cutter_for_feature(cq, feature, through_depth))

    outer_wire = cq.Workplane("XY").rect(width, height, centered=False).val()
    inner_wires = [_inner_wire_for_feature(cq, feature) for feature in spec.features]
    midsurface_face = cq.Face.makeFromWires(outer_wire, inner_wires)
    reference_midsurface = cq.Workplane("XY").newObject([midsurface_face])

    return GeneratedFlatPanel(
        spec=spec,
        solid_shape=solid,
        reference_midsurface_shape=reference_midsurface,
        feature_truth=feature_truth,
        generator_params=generator_params,
    )


def export_step(shape: Any, path: str | Path, part_name: str | None = None) -> None:
    """Export a CadQuery shape to STEP."""

    if shape is None:
        raise FlatPanelBuildError("missing_shape", "shape is required for STEP export")
    _ = part_name
    cq = _load_cadquery()
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(output_path))


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_flat_panel_outputs(sample_root: str | Path, generated: GeneratedFlatPanel) -> dict[str, str]:
    """Write T-201 CAD and metadata outputs below a sample directory."""

    root = Path(sample_root)
    input_step = root / "cad" / "input.step"
    midsurface_step = root / "cad" / "reference_midsurface.step"
    feature_truth_json = root / "metadata" / "feature_truth.json"
    generator_params_json = root / "metadata" / "generator_params.json"

    export_step(generated.solid_shape, input_step, generated.spec.part_name)
    export_step(generated.reference_midsurface_shape, midsurface_step, generated.spec.part_name)
    _write_json(feature_truth_json, generated.feature_truth.model_dump(mode="json"))
    _write_json(generator_params_json, generated.generator_params)

    return {
        "input_step": input_step.as_posix(),
        "reference_midsurface_step": midsurface_step.as_posix(),
        "feature_truth": feature_truth_json.as_posix(),
        "generator_params": generator_params_json.as_posix(),
    }
