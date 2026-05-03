"""Pydantic domain models shared by CDF writers."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CdfBaseModel(BaseModel):
    """Base model with strict fields and JSON-friendly dumps."""

    model_config = ConfigDict(extra="forbid")

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PartClass(str, Enum):
    SM_FLAT_PANEL = "SM_FLAT_PANEL"
    SM_SINGLE_FLANGE = "SM_SINGLE_FLANGE"
    SM_L_BRACKET = "SM_L_BRACKET"
    SM_U_CHANNEL = "SM_U_CHANNEL"
    SM_HAT_CHANNEL = "SM_HAT_CHANNEL"


class FeatureType(str, Enum):
    HOLE = "HOLE"
    SLOT = "SLOT"
    CUTOUT = "CUTOUT"
    BEND = "BEND"
    FLANGE = "FLANGE"
    OUTER_BOUNDARY = "OUTER_BOUNDARY"


class FeatureRole(str, Enum):
    BOLT = "BOLT"
    MOUNT = "MOUNT"
    RELIEF = "RELIEF"
    DRAIN = "DRAIN"
    VENT = "VENT"
    PASSAGE = "PASSAGE"
    STRUCTURAL = "STRUCTURAL"
    UNKNOWN = "UNKNOWN"


class ManifestAction(str, Enum):
    KEEP_REFINED = "KEEP_REFINED"
    KEEP_WITH_WASHER = "KEEP_WITH_WASHER"
    SUPPRESS = "SUPPRESS"
    KEEP_WITH_BEND_ROWS = "KEEP_WITH_BEND_ROWS"
    KEEP_WITH_FLANGE_SIZE = "KEEP_WITH_FLANGE_SIZE"


class ManifestStatus(str, Enum):
    VALID = "VALID"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    MESH_FAILED = "MESH_FAILED"


class PartParams(CdfBaseModel):
    part_name: str
    part_class: PartClass
    unit: Literal["mm"] = "mm"
    thickness_mm: float = Field(gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    corner_radius_mm: float | None = Field(default=None, ge=0)


class MeshPolicy(CdfBaseModel):
    h0_mm: float = Field(gt=0)
    h_min_mm: float = Field(gt=0)
    h_max_mm: float = Field(gt=0)
    growth_rate_max: float = Field(gt=1)
    quality_profile: Literal["AMG_QA_SHELL_V1"] = "AMG_QA_SHELL_V1"

    @model_validator(mode="after")
    def validate_bounds(self) -> MeshPolicy:
        if self.h_min_mm > self.h_max_mm:
            raise ValueError("h_min_mm must be <= h_max_mm")
        return self


class FeatureTruthBase(CdfBaseModel):
    feature_id: str
    role: FeatureRole
    created_by: str


class HoleTruth(FeatureTruthBase):
    type: Literal["HOLE"] = "HOLE"
    center_uv_mm: tuple[float, float] | None = None
    center_mm: tuple[float, float, float] | None = None
    axis: tuple[float, float, float] | None = None
    radius_mm: float = Field(gt=0)
    patch_id: str | None = None
    axis_source: str | None = None


class SlotTruth(FeatureTruthBase):
    type: Literal["SLOT"] = "SLOT"
    center_uv_mm: tuple[float, float]
    width_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)
    angle_deg: float = 0.0
    patch_id: str
    axis_source: str | None = None

    @model_validator(mode="after")
    def validate_length(self) -> SlotTruth:
        if self.length_mm < self.width_mm:
            raise ValueError("length_mm must be >= width_mm")
        return self


class CutoutTruth(FeatureTruthBase):
    type: Literal["CUTOUT"] = "CUTOUT"
    center_uv_mm: tuple[float, float]
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    corner_radius_mm: float = Field(default=0.0, ge=0)
    angle_deg: float = 0.0
    patch_id: str
    axis_source: str | None = None


class BendTruth(FeatureTruthBase):
    type: Literal["BEND"] = "BEND"
    inner_radius_mm: float = Field(gt=0)
    angle_deg: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    adjacent_patch_ids: tuple[str, str]


class FlangeTruth(FeatureTruthBase):
    type: Literal["FLANGE"] = "FLANGE"
    width_mm: float = Field(gt=0)
    free_edge_id: str
    bend_id: str


FeatureTruth: TypeAlias = Annotated[
    HoleTruth | SlotTruth | CutoutTruth | BendTruth | FlangeTruth,
    Field(discriminator="type"),
]


class FeatureTruthDocument(CdfBaseModel):
    schema_version: Literal["CDF_FEATURE_TRUTH_SM_V1"] = "CDF_FEATURE_TRUTH_SM_V1"
    sample_id: str
    part: PartParams
    features: list[FeatureTruth]


class FeatureEntitySignature(CdfBaseModel):
    feature_id: str
    type: FeatureType
    role: FeatureRole
    signature: dict[str, Any]


class EntitySignaturesDocument(CdfBaseModel):
    schema_version: Literal["CDF_ENTITY_SIGNATURES_SM_V1"] = "CDF_ENTITY_SIGNATURES_SM_V1"
    sample_id: str
    part_name: str
    features: list[FeatureEntitySignature]


class HoleRefinedControl(CdfBaseModel):
    edge_target_length_mm: float = Field(gt=0)
    circumferential_divisions: int = Field(gt=0)
    radial_growth_rate: float = Field(gt=1)


class HoleWasherControl(HoleRefinedControl):
    washer_rings: int = Field(ge=1)
    washer_outer_radius_mm: float = Field(gt=0)


class SlotControl(CdfBaseModel):
    edge_target_length_mm: float = Field(gt=0)
    end_arc_divisions: int | None = Field(default=None, gt=0)
    slot_end_divisions: int | None = Field(default=None, gt=0)
    straight_edge_divisions: int = Field(gt=0)
    growth_rate: float = Field(gt=1)

    @model_validator(mode="after")
    def validate_end_divisions(self) -> SlotControl:
        if self.end_arc_divisions is None and self.slot_end_divisions is None:
            raise ValueError("end_arc_divisions or slot_end_divisions is required")
        return self


class CutoutControl(CdfBaseModel):
    edge_target_length_mm: float = Field(gt=0)
    perimeter_growth_rate: float = Field(gt=1)


class BendControl(CdfBaseModel):
    bend_rows: int = Field(gt=0)
    bend_target_length_mm: float = Field(gt=0)
    growth_rate: float = Field(gt=1)


class FlangeControl(CdfBaseModel):
    flange_target_length_mm: float | None = Field(default=None, gt=0)
    free_edge_target_length_mm: float | None = Field(default=None, gt=0)
    min_elements_across_width: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_target_length(self) -> FlangeControl:
        if self.flange_target_length_mm is None and self.free_edge_target_length_mm is None:
            raise ValueError("flange_target_length_mm or free_edge_target_length_mm is required")
        return self


class SuppressionControl(CdfBaseModel):
    reason: str | None = None
    suppression_rule: str | None = None

    @model_validator(mode="after")
    def validate_reason(self) -> SuppressionControl:
        if self.reason is None and self.suppression_rule is None:
            raise ValueError("reason or suppression_rule is required")
        return self


ManifestControls: TypeAlias = (
    HoleWasherControl
    | HoleRefinedControl
    | SlotControl
    | CutoutControl
    | BendControl
    | FlangeControl
    | SuppressionControl
)


class ManifestFeatureRecord(CdfBaseModel):
    feature_id: str
    type: FeatureType
    role: FeatureRole
    action: ManifestAction
    controls: ManifestControls
    geometry_signature: dict[str, Any] | None = None
