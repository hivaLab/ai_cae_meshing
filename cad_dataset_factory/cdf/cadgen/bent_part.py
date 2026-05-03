"""Deterministic CadQuery bent sheet-metal generators for CDF."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field

from cad_dataset_factory.cdf.domain import (
    BendTruth,
    CdfBaseModel,
    FeatureRole,
    FeatureTruthDocument,
    FlangeTruth,
    PartClass,
    PartParams,
)

SUPPORTED_PART_CLASSES = {
    PartClass.SM_SINGLE_FLANGE,
    PartClass.SM_L_BRACKET,
    PartClass.SM_U_CHANNEL,
    PartClass.SM_HAT_CHANNEL,
}


class BentPartBuildError(ValueError):
    """Raised when a bent sheet-metal part cannot be generated safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


class BentPartSpec(CdfBaseModel):
    sample_id: str
    part_name: str
    part_class: PartClass
    unit: str = "mm"
    length_mm: float = Field(gt=0)
    web_width_mm: float = Field(gt=0)
    flange_width_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    inner_radius_mm: float = Field(gt=0)
    bend_angle_deg: float = 90.0
    side_wall_width_mm: float | None = Field(default=None, gt=0)


@dataclass(frozen=True)
class GeneratedBentPart:
    spec: BentPartSpec
    solid_shape: Any
    reference_midsurface_shape: Any
    feature_truth: FeatureTruthDocument
    generator_params: dict[str, Any]


def _load_cadquery() -> Any:
    try:
        import cadquery as cq
    except ModuleNotFoundError as exc:
        raise BentPartBuildError(
            "cadquery_unavailable",
            "CadQuery is required for bent-part CAD build/export; install the cad optional dependency",
        ) from exc
    return cq


def _part_class_value(part_class: PartClass | str) -> str:
    return part_class.value if isinstance(part_class, PartClass) else str(part_class)


def _validate_spec(spec: BentPartSpec) -> None:
    if spec.unit != "mm":
        raise BentPartBuildError("unsupported_unit", "T-202 bent parts require unit mm")
    if _part_class_value(spec.part_class) not in {part_class.value for part_class in SUPPORTED_PART_CLASSES}:
        raise BentPartBuildError("unsupported_part_class", "T-202 supports bent sheet-metal part classes only")
    if not 45.0 <= spec.bend_angle_deg <= 120.0:
        raise BentPartBuildError("invalid_bend_angle", "bend_angle_deg must be between 45 and 120")
    if spec.inner_radius_mm < 0.5 * spec.thickness_mm:
        raise BentPartBuildError("invalid_bend_radius", "inner_radius_mm must be >= 0.5 * thickness_mm")
    if spec.flange_width_mm < 2.0 * spec.thickness_mm:
        raise BentPartBuildError("invalid_flange_width", "flange_width_mm must be >= 2 * thickness_mm")
    if spec.part_class == PartClass.SM_HAT_CHANNEL:
        _hat_side_wall_width(spec)


def _hat_side_wall_width(spec: BentPartSpec) -> float:
    side_wall_width = spec.side_wall_width_mm if spec.side_wall_width_mm is not None else spec.flange_width_mm
    if side_wall_width < 2.0 * spec.thickness_mm:
        raise BentPartBuildError("invalid_side_wall_width", "side_wall_width_mm must be >= 2 * thickness_mm")
    return side_wall_width


def _cross_section_points(spec: BentPartSpec) -> list[tuple[float, float]]:
    t = spec.thickness_mm
    web = spec.web_width_mm
    flange = spec.flange_width_mm

    if spec.part_class in {PartClass.SM_SINGLE_FLANGE, PartClass.SM_L_BRACKET}:
        return [
            (0.0, 0.0),
            (web, 0.0),
            (web, flange),
            (web - t, flange),
            (web - t, t),
            (0.0, t),
        ]

    if spec.part_class == PartClass.SM_U_CHANNEL:
        return [
            (0.0, 0.0),
            (web, 0.0),
            (web, flange),
            (web - t, flange),
            (web - t, t),
            (t, t),
            (t, flange),
            (0.0, flange),
        ]

    if spec.part_class == PartClass.SM_HAT_CHANNEL:
        side = _hat_side_wall_width(spec)
        total_y = flange + web + flange
        return [
            (0.0, 0.0),
            (flange + t, 0.0),
            (flange + t, side),
            (flange + web - t, side),
            (flange + web - t, 0.0),
            (total_y, 0.0),
            (total_y, t),
            (flange + web, t),
            (flange + web, side + t),
            (flange, side + t),
            (flange, t),
            (0.0, t),
        ]

    raise BentPartBuildError("unsupported_part_class", "T-202 supports bent sheet-metal part classes only")


def _centerline_points(spec: BentPartSpec) -> list[tuple[float, float]]:
    t = spec.thickness_mm
    half_t = t / 2.0
    web = spec.web_width_mm
    flange = spec.flange_width_mm

    if spec.part_class in {PartClass.SM_SINGLE_FLANGE, PartClass.SM_L_BRACKET}:
        return [
            (0.0, half_t),
            (web - half_t, half_t),
            (web - half_t, flange - half_t),
        ]

    if spec.part_class == PartClass.SM_U_CHANNEL:
        return [
            (half_t, flange - half_t),
            (half_t, half_t),
            (web - half_t, half_t),
            (web - half_t, flange - half_t),
        ]

    if spec.part_class == PartClass.SM_HAT_CHANNEL:
        side = _hat_side_wall_width(spec)
        total_y = flange + web + flange
        return [
            (0.0, half_t),
            (flange + half_t, half_t),
            (flange + half_t, side + half_t),
            (flange + web - half_t, side + half_t),
            (flange + web - half_t, half_t),
            (total_y, half_t),
        ]

    raise BentPartBuildError("unsupported_part_class", "T-202 supports bent sheet-metal part classes only")


def _bend_adjacencies(spec: BentPartSpec) -> list[tuple[str, str]]:
    if spec.part_class in {PartClass.SM_SINGLE_FLANGE, PartClass.SM_L_BRACKET}:
        return [("PATCH_WEB_0001", "PATCH_FLANGE_0001")]
    if spec.part_class == PartClass.SM_U_CHANNEL:
        return [
            ("PATCH_FLANGE_0001", "PATCH_WEB_0001"),
            ("PATCH_WEB_0001", "PATCH_FLANGE_0002"),
        ]
    if spec.part_class == PartClass.SM_HAT_CHANNEL:
        return [
            ("PATCH_FLANGE_0001", "PATCH_SIDEWALL_0001"),
            ("PATCH_SIDEWALL_0001", "PATCH_WEB_0001"),
            ("PATCH_WEB_0001", "PATCH_SIDEWALL_0002"),
            ("PATCH_SIDEWALL_0002", "PATCH_FLANGE_0002"),
        ]
    raise BentPartBuildError("unsupported_part_class", "T-202 supports bent sheet-metal part classes only")


def _flange_records(spec: BentPartSpec, bend_ids: list[str]) -> list[FlangeTruth]:
    if spec.part_class in {PartClass.SM_SINGLE_FLANGE, PartClass.SM_L_BRACKET}:
        return [
            FlangeTruth(
                feature_id="FLANGE_STRUCTURAL_0001",
                role=FeatureRole.STRUCTURAL,
                created_by="cadgen.bent_part.flange",
                width_mm=spec.flange_width_mm,
                free_edge_id="EDGE_FLANGE_FREE_0001",
                bend_id=bend_ids[0],
            )
        ]

    if spec.part_class == PartClass.SM_U_CHANNEL:
        return [
            FlangeTruth(
                feature_id="FLANGE_STRUCTURAL_0001",
                role=FeatureRole.STRUCTURAL,
                created_by="cadgen.bent_part.flange",
                width_mm=spec.flange_width_mm,
                free_edge_id="EDGE_FLANGE_FREE_0001",
                bend_id=bend_ids[0],
            ),
            FlangeTruth(
                feature_id="FLANGE_STRUCTURAL_0002",
                role=FeatureRole.STRUCTURAL,
                created_by="cadgen.bent_part.flange",
                width_mm=spec.flange_width_mm,
                free_edge_id="EDGE_FLANGE_FREE_0002",
                bend_id=bend_ids[1],
            ),
        ]

    if spec.part_class == PartClass.SM_HAT_CHANNEL:
        side = _hat_side_wall_width(spec)
        return [
            FlangeTruth(
                feature_id=f"FLANGE_STRUCTURAL_{index:04d}",
                role=FeatureRole.STRUCTURAL,
                created_by="cadgen.bent_part.flange",
                width_mm=side,
                free_edge_id=f"EDGE_FLANGE_FREE_{index:04d}",
                bend_id=bend_id,
            )
            for index, bend_id in enumerate(bend_ids, start=1)
        ]

    raise BentPartBuildError("unsupported_part_class", "T-202 supports bent sheet-metal part classes only")


def _build_feature_truth(spec: BentPartSpec) -> FeatureTruthDocument:
    bend_adjacencies = _bend_adjacencies(spec)
    bend_ids = [f"BEND_STRUCTURAL_{index:04d}" for index in range(1, len(bend_adjacencies) + 1)]
    bends = [
        BendTruth(
            feature_id=bend_id,
            role=FeatureRole.STRUCTURAL,
            created_by="cadgen.bent_part.bend",
            inner_radius_mm=spec.inner_radius_mm,
            angle_deg=spec.bend_angle_deg,
            thickness_mm=spec.thickness_mm,
            adjacent_patch_ids=adjacency,
        )
        for bend_id, adjacency in zip(bend_ids, bend_adjacencies, strict=True)
    ]
    flanges = _flange_records(spec, bend_ids)
    return FeatureTruthDocument(
        sample_id=spec.sample_id,
        part=PartParams(
            part_name=spec.part_name,
            part_class=spec.part_class,
            thickness_mm=spec.thickness_mm,
            width_mm=spec.length_mm,
            height_mm=spec.web_width_mm,
        ),
        features=[*bends, *flanges],
    )


def _generator_params(spec: BentPartSpec) -> dict[str, Any]:
    return {
        "schema": "CDF_GENERATOR_PARAMS_SM_V1",
        "sample_id": spec.sample_id,
        "part_class": _part_class_value(spec.part_class),
        "canonical_part_name": spec.part_name,
        "length_mm": spec.length_mm,
        "web_width_mm": spec.web_width_mm,
        "flange_width_mm": spec.flange_width_mm,
        "side_wall_width_mm": spec.side_wall_width_mm,
        "thickness_mm": spec.thickness_mm,
        "inner_radius_mm": spec.inner_radius_mm,
        "bend_angle_deg": spec.bend_angle_deg,
    }


def build_bent_part(spec: BentPartSpec) -> GeneratedBentPart:
    """Build a deterministic bent sheet-metal part and its truth records."""

    _validate_spec(spec)
    feature_truth = _build_feature_truth(spec)
    generator_params = _generator_params(spec)
    cq = _load_cadquery()

    solid = cq.Workplane("YZ").polyline(_cross_section_points(spec)).close().extrude(spec.length_mm)
    centerline = cq.Workplane("YZ").polyline(_centerline_points(spec)).val()
    reference_midsurface = cq.Workplane("YZ").newObject([centerline])

    return GeneratedBentPart(
        spec=spec,
        solid_shape=solid,
        reference_midsurface_shape=reference_midsurface,
        feature_truth=feature_truth,
        generator_params=generator_params,
    )


def _export_step(shape: Any, path: str | Path) -> None:
    if shape is None:
        raise BentPartBuildError("missing_shape", "shape is required for STEP export")
    cq = _load_cadquery()
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(output_path))


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_bent_part_outputs(sample_root: str | Path, generated: GeneratedBentPart) -> dict[str, str]:
    """Write T-202 CAD and metadata outputs below a sample directory."""

    root = Path(sample_root)
    input_step = root / "cad" / "input.step"
    midsurface_step = root / "cad" / "reference_midsurface.step"
    feature_truth_json = root / "metadata" / "feature_truth.json"
    generator_params_json = root / "metadata" / "generator_params.json"

    _export_step(generated.solid_shape, input_step)
    _export_step(generated.reference_midsurface_shape, midsurface_step)
    _write_json(feature_truth_json, generated.feature_truth.model_dump(mode="json"))
    _write_json(generator_params_json, generated.generator_params)

    return {
        "input_step": input_step.as_posix(),
        "reference_midsurface_step": midsurface_step.as_posix(),
        "feature_truth": feature_truth_json.as_posix(),
        "generator_params": generator_params_json.as_posix(),
    }
