"""Pydantic domain models shared by CDF writers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


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
