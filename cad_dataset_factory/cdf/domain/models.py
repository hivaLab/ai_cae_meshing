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
    quality_profile: Literal["AMG_QA_SHELL_V2"] = "AMG_QA_SHELL_V2"

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
