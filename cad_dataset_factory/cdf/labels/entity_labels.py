"""Entity-level labels for the B-rep native AMG v2 pipeline."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Self

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityLabelError(ValueError):
    """Raised when an entity-label document is malformed or cannot be written."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


class PartClass(StrEnum):
    SM_FLAT_PANEL = "SM_FLAT_PANEL"
    SM_SINGLE_FLANGE = "SM_SINGLE_FLANGE"
    SM_L_BRACKET = "SM_L_BRACKET"
    SM_U_CHANNEL = "SM_U_CHANNEL"
    SM_HAT_CHANNEL = "SM_HAT_CHANNEL"
    OTHER = "OTHER"


class FaceSemanticLabel(StrEnum):
    BASE_PANEL = "BASE_PANEL"
    FLANGE = "FLANGE"
    HOLE_WALL = "HOLE_WALL"
    SLOT_WALL = "SLOT_WALL"
    CUTOUT_WALL = "CUTOUT_WALL"
    SIDE_WALL = "SIDE_WALL"
    OTHER = "OTHER"


class EdgeSemanticLabel(StrEnum):
    OUTER_BOUNDARY = "OUTER_BOUNDARY"
    HOLE_BOUNDARY = "HOLE_BOUNDARY"
    SLOT_BOUNDARY = "SLOT_BOUNDARY"
    CUTOUT_BOUNDARY = "CUTOUT_BOUNDARY"
    BEND_EDGE = "BEND_EDGE"
    FREE_EDGE = "FREE_EDGE"
    INTERNAL = "INTERNAL"
    OTHER = "OTHER"


class EntityType(StrEnum):
    EDGE = "EDGE"
    FACE = "FACE"


class JsonModel(BaseModel):
    """Base model that serializes cleanly through ``model_dump(mode='json')``."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class PartClassLabelDocument(JsonModel):
    schema_version: str = "CDF_PART_CLASS_LABEL_SM_V2"
    sample_id: str = Field(min_length=1)
    part_class: PartClass
    source: str = Field(min_length=1)


class FaceSegmentationLabel(JsonModel):
    face_signature_id: str = Field(min_length=1)
    semantic_label: FaceSemanticLabel
    instance_id: str | None = None


class FaceSegmentationDocument(JsonModel):
    schema_version: str = "CDF_FACE_SEGMENTATION_SM_V2"
    sample_id: str = Field(min_length=1)
    labels: tuple[FaceSegmentationLabel, ...] = ()

    @model_validator(mode="after")
    def _unique_face_ids(self) -> Self:
        _assert_unique([label.face_signature_id for label in self.labels], "duplicate_face_signature_id")
        return self


class EdgeSegmentationLabel(JsonModel):
    edge_signature_id: str = Field(min_length=1)
    semantic_label: EdgeSemanticLabel
    instance_id: str | None = None


class EdgeSegmentationDocument(JsonModel):
    schema_version: str = "CDF_EDGE_SEGMENTATION_SM_V2"
    sample_id: str = Field(min_length=1)
    labels: tuple[EdgeSegmentationLabel, ...] = ()

    @model_validator(mode="after")
    def _unique_edge_ids(self) -> Self:
        _assert_unique([label.edge_signature_id for label in self.labels], "duplicate_edge_signature_id")
        return self


class GlobalMeshPolicy(JsonModel):
    h0_mm: float = Field(gt=0)
    h_min_mm: float = Field(gt=0)
    h_max_mm: float = Field(gt=0)
    growth_rate: float = Field(ge=1.0)
    quality_profile: str = Field(min_length=1)

    @model_validator(mode="after")
    def _valid_bounds(self) -> Self:
        if self.h_min_mm > self.h_max_mm:
            raise ValueError("h_min_mm must be <= h_max_mm")
        if not (self.h_min_mm <= self.h0_mm <= self.h_max_mm):
            raise ValueError("h0_mm must be within [h_min_mm, h_max_mm]")
        return self


class EdgeSizeRecord(JsonModel):
    edge_signature_id: str = Field(min_length=1)
    target_size_mm: float = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None


class FaceSizeRecord(JsonModel):
    face_signature_id: str = Field(min_length=1)
    target_size_mm: float = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None


class MeshSizeFieldDocument(JsonModel):
    schema_version: str = "CDF_MESH_SIZE_FIELD_SM_V2"
    sample_id: str = Field(min_length=1)
    cad_file: str = Field(default="cad/input.step", min_length=1)
    unit: str = "mm"
    global_mesh: GlobalMeshPolicy
    edge_sizes: tuple[EdgeSizeRecord, ...] = ()
    face_sizes: tuple[FaceSizeRecord, ...] = ()

    @model_validator(mode="after")
    def _valid_size_field(self) -> Self:
        if self.unit != "mm":
            raise ValueError("unit must be mm")
        _assert_unique([record.edge_signature_id for record in self.edge_sizes], "duplicate_edge_signature_id")
        _assert_unique([record.face_signature_id for record in self.face_sizes], "duplicate_face_signature_id")
        for record in (*self.edge_sizes, *self.face_sizes):
            if not (self.global_mesh.h_min_mm <= record.target_size_mm <= self.global_mesh.h_max_mm):
                raise ValueError("target_size_mm must be within global mesh bounds")
        return self


class EntityQualityRecord(JsonModel):
    entity_signature_id: str = Field(min_length=1)
    entity_type: EntityType
    semantic_label: str | None = None
    candidate_target_size_mm: float = Field(gt=0)
    candidate_neighbor_size_ratio_max: float | None = Field(default=None, ge=1)
    candidate_growth_rate: float = Field(ge=1)
    measured_quality_margin: float
    measured_edge_length_mean_mm: float | None = Field(default=None, gt=0)
    measured_edge_length_min_mm: float | None = Field(default=None, gt=0)
    measured_edge_length_max_mm: float | None = Field(default=None, gt=0)
    measured_edge_segment_count: int | None = Field(default=None, ge=1)
    measured_boundary_size_error: float | None = Field(default=None, ge=0)
    hard_fail: bool
    near_fail: bool
    metric_available: bool
    metric_unavailable_reason: str | None = None

    @model_validator(mode="after")
    def _availability_reason(self) -> Self:
        if not self.metric_available and not self.metric_unavailable_reason:
            raise ValueError("metric_unavailable_reason is required when metric_available=false")
        if self.metric_available and self.metric_unavailable_reason:
            raise ValueError("metric_unavailable_reason must be omitted when metric_available=true")
        return self


class EntityQualityEvaluationDocument(JsonModel):
    schema_version: str = "CDF_ENTITY_QUALITY_EVALUATION_SM_V2"
    sample_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    size_field_path: str = Field(min_length=1)
    entity_quality: tuple[EntityQualityRecord, ...]
    global_quality_summary: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _nonempty_entity_quality(self) -> Self:
        if not self.entity_quality:
            raise ValueError("entity_quality must contain at least one row")
        return self


SCHEMA_BY_VERSION: dict[str, str] = {
    "CDF_PART_CLASS_LABEL_SM_V2": "CDF_PART_CLASS_LABEL_SM_V2.schema.json",
    "CDF_FACE_SEGMENTATION_SM_V2": "CDF_FACE_SEGMENTATION_SM_V2.schema.json",
    "CDF_EDGE_SEGMENTATION_SM_V2": "CDF_EDGE_SEGMENTATION_SM_V2.schema.json",
    "CDF_MESH_SIZE_FIELD_SM_V2": "CDF_MESH_SIZE_FIELD_SM_V2.schema.json",
    "CDF_ENTITY_QUALITY_EVALUATION_SM_V2": "CDF_ENTITY_QUALITY_EVALUATION_SM_V2.schema.json",
}


def _assert_unique(values: list[str], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema(schema_file: str) -> dict[str, Any]:
    return json.loads((_repo_root() / "contracts" / schema_file).read_text(encoding="utf-8"))


def _json_object(document: JsonModel | dict[str, Any]) -> dict[str, Any]:
    raw = document.model_dump(mode="json", exclude_none=True) if isinstance(document, JsonModel) else document
    normalized = json.loads(json.dumps(raw, allow_nan=False))
    if not isinstance(normalized, dict):
        raise EntityLabelError("document_not_object", "entity-label document must be a JSON object")
    return normalized


def validate_entity_label_document(document: JsonModel | dict[str, Any]) -> dict[str, Any]:
    """Validate an entity-label document against its versioned JSON schema."""

    normalized = _json_object(document)
    schema_version = normalized.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in SCHEMA_BY_VERSION:
        raise EntityLabelError("unknown_schema_version", "unknown or missing schema_version")
    validator = Draft202012Validator(_schema(SCHEMA_BY_VERSION[schema_version]))
    errors = sorted(validator.iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise EntityLabelError("schema_validation_failed", f"{location}: {first.message}")
    return normalized


def write_entity_label_json(path: str | Path, document: JsonModel | dict[str, Any]) -> None:
    """Write a schema-valid entity-label JSON document."""

    normalized = validate_entity_label_document(document)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
