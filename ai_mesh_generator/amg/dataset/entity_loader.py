"""AMG v2 entity dataset loader.

This loader consumes CDF outputs only through versioned files. It never imports CDF.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

ENTITY_GRAPH_SCHEMA_VERSION = "AMG_BREP_ENTITY_GRAPH_SM_V2"
PART_LABEL_SCHEMA_VERSION = "CDF_PART_CLASS_LABEL_SM_V2"
FACE_LABEL_SCHEMA_VERSION = "CDF_FACE_SEGMENTATION_SM_V2"
EDGE_LABEL_SCHEMA_VERSION = "CDF_EDGE_SEGMENTATION_SM_V2"
SIZE_FIELD_SCHEMA_VERSION = "CDF_MESH_SIZE_FIELD_SM_V2"
QUALITY_EVALUATION_SCHEMA_VERSION = "CDF_ENTITY_QUALITY_EVALUATION_SM_V2"

CORE_ENTITY_GRAPH_ARRAYS = (
    "part_features",
    "face_features",
    "edge_features",
    "coedge_features",
    "vertex_features",
)
LEAKAGE_TOKENS = (
    "target",
    "label",
    "quality",
    "action",
    "washer",
    "suppress",
    "bend_rows",
    "circumferential_divisions",
)


class EntityDatasetLoadError(ValueError):
    """Raised when an entity dataset file cannot be loaded safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class EntityBrepGraphInput:
    sample_id: str
    sample_dir: Path
    arrays: dict[str, np.ndarray]
    adjacency: dict[str, np.ndarray]
    graph_schema: dict[str, Any]
    entity_signatures: dict[str, Any]
    model_input_paths: dict[str, str]


@dataclass(frozen=True)
class EntityLabelSet:
    part_class: dict[str, Any]
    face_segmentation: dict[str, Any]
    edge_segmentation: dict[str, Any]
    mesh_size_field: dict[str, Any]
    quality_evaluations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class EntityDatasetSample:
    sample_id: str
    sample_dir: Path
    graph: EntityBrepGraphInput
    labels: EntityLabelSet
    model_input_paths: dict[str, str]
    label_paths: dict[str, str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema(schema_version: str) -> dict[str, Any]:
    return _read_json(_repo_root() / "contracts" / f"{schema_version}.schema.json", "schema_read_failed")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EntityDatasetLoadError(code, f"could not read JSON file: {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise EntityDatasetLoadError("json_parse_failed", f"could not parse JSON file: {path}", path) from exc
    if not isinstance(loaded, dict):
        raise EntityDatasetLoadError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _require_file(path: Path, code: str) -> None:
    if not path.is_file():
        raise EntityDatasetLoadError(code, f"required file does not exist: {path}", path)


def _validate_schema(document: dict[str, Any], schema_version: str, code: str, path: Path) -> dict[str, Any]:
    if document.get("schema_version") != schema_version:
        raise EntityDatasetLoadError(code, f"schema_version must be {schema_version}", path)
    validator = Draft202012Validator(_schema(schema_version))
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise EntityDatasetLoadError(code, f"{schema_version} {location}: {first.message}", path)
    return json.loads(json.dumps(document, allow_nan=False))


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    _require_file(path, "missing_entity_graph")
    try:
        loaded = np.load(path, allow_pickle=False)
    except OSError as exc:
        raise EntityDatasetLoadError("entity_graph_read_failed", f"could not read graph npz: {path}", path) from exc
    with loaded:
        return {key: np.array(loaded[key], copy=True) for key in loaded.files}


def _validate_no_graph_leakage(graph_schema: Mapping[str, Any], arrays: Mapping[str, np.ndarray], path: Path) -> None:
    column_fields = (
        "part_feature_columns",
        "face_feature_columns",
        "edge_feature_columns",
        "coedge_feature_columns",
        "vertex_feature_columns",
    )
    for field in column_fields:
        for column in graph_schema.get(field, []):
            lowered = str(column).lower()
            if any(token in lowered for token in LEAKAGE_TOKENS):
                raise EntityDatasetLoadError("graph_target_leakage", f"forbidden graph input column: {column}", path)
    for key in arrays:
        lowered = key.lower()
        if any(token in lowered for token in LEAKAGE_TOKENS):
            raise EntityDatasetLoadError("graph_target_leakage", f"forbidden graph input array: {key}", path)


def load_entity_brep_graph_input(sample_dir: str | Path) -> EntityBrepGraphInput:
    sample_path = Path(sample_dir)
    if not sample_path.is_dir():
        raise EntityDatasetLoadError("missing_sample_dir", f"sample directory does not exist: {sample_path}", sample_path)
    graph_path = sample_path / "graph" / "brep_graph.npz"
    schema_path = sample_path / "graph" / "graph_schema.json"
    signatures_path = sample_path / "graph" / "entity_signatures.json"
    _require_file(schema_path, "missing_graph_schema")
    _require_file(signatures_path, "missing_entity_signatures")
    graph_schema = _validate_schema(_read_json(schema_path, "graph_schema_read_failed"), ENTITY_GRAPH_SCHEMA_VERSION, "graph_schema_invalid", schema_path)
    arrays = _load_npz(graph_path)
    for key in CORE_ENTITY_GRAPH_ARRAYS:
        if key not in arrays:
            raise EntityDatasetLoadError("missing_graph_array", f"missing graph array: {key}", graph_path)
        if arrays[key].ndim != 2:
            raise EntityDatasetLoadError("malformed_graph_array", f"{key} must be a 2D array", graph_path)
    adjacency: dict[str, np.ndarray] = {}
    for edge_type in graph_schema["edge_types"]:
        key = f"adj_{edge_type}"
        if key not in arrays:
            raise EntityDatasetLoadError("missing_adjacency_array", f"missing adjacency array: {key}", graph_path)
        adjacency_array = arrays[key]
        if adjacency_array.ndim != 2 or adjacency_array.shape[1] != 2 or not np.issubdtype(adjacency_array.dtype, np.integer):
            raise EntityDatasetLoadError("malformed_adjacency_array", f"{key} must be an integer Nx2 array", graph_path)
        adjacency[edge_type] = adjacency_array
    _validate_no_graph_leakage(graph_schema, arrays, graph_path)
    signatures = _read_json(signatures_path, "entity_signatures_read_failed")
    if len(signatures.get("faces", [])) != arrays["face_features"].shape[0]:
        raise EntityDatasetLoadError("malformed_entity_signatures", "face signature count must match face rows", signatures_path)
    if len(signatures.get("edges", [])) != arrays["edge_features"].shape[0]:
        raise EntityDatasetLoadError("malformed_entity_signatures", "edge signature count must match edge rows", signatures_path)
    return EntityBrepGraphInput(
        sample_id=sample_path.name,
        sample_dir=sample_path,
        arrays=arrays,
        adjacency=adjacency,
        graph_schema=graph_schema,
        entity_signatures=signatures,
        model_input_paths={
            "brep_graph": graph_path.as_posix(),
            "graph_schema": schema_path.as_posix(),
            "entity_signatures": signatures_path.as_posix(),
        },
    )


def _load_label(path: Path, schema_version: str, missing_code: str, invalid_code: str) -> dict[str, Any]:
    _require_file(path, missing_code)
    return _validate_schema(_read_json(path, f"{invalid_code}_read_failed"), schema_version, invalid_code, path)


def load_entity_label_set(sample_dir: str | Path, *, require_quality: bool = False) -> EntityLabelSet:
    sample_path = Path(sample_dir)
    labels = sample_path / "labels"
    metadata = sample_path / "metadata"
    part = _load_label(metadata / "part_class_label.json", PART_LABEL_SCHEMA_VERSION, "missing_part_class_label", "part_class_label_invalid")
    face = _load_label(labels / "face_segmentation.json", FACE_LABEL_SCHEMA_VERSION, "missing_face_segmentation", "face_segmentation_invalid")
    edge = _load_label(labels / "edge_segmentation.json", EDGE_LABEL_SCHEMA_VERSION, "missing_edge_segmentation", "edge_segmentation_invalid")
    size = _load_label(labels / "mesh_size_field.json", SIZE_FIELD_SCHEMA_VERSION, "missing_mesh_size_field", "mesh_size_field_invalid")
    quality_docs: list[dict[str, Any]] = []
    quality_root = sample_path / "quality_evaluations"
    if quality_root.exists():
        for path in sorted(quality_root.glob("*/entity_quality_labels.json")):
            quality_docs.append(_load_label(path, QUALITY_EVALUATION_SCHEMA_VERSION, "missing_entity_quality", "entity_quality_invalid"))
    if require_quality and not quality_docs:
        raise EntityDatasetLoadError("missing_entity_quality", "at least one entity quality evaluation is required", quality_root)
    return EntityLabelSet(part_class=part, face_segmentation=face, edge_segmentation=edge, mesh_size_field=size, quality_evaluations=tuple(quality_docs))


def load_entity_dataset_sample(sample_dir: str | Path, *, require_quality: bool = False) -> EntityDatasetSample:
    graph = load_entity_brep_graph_input(sample_dir)
    labels = load_entity_label_set(sample_dir, require_quality=require_quality)
    sample_ids = {
        labels.part_class["sample_id"],
        labels.face_segmentation["sample_id"],
        labels.edge_segmentation["sample_id"],
        labels.mesh_size_field["sample_id"],
    }
    sample_ids.update(doc["sample_id"] for doc in labels.quality_evaluations)
    if sample_ids != {graph.sample_id}:
        raise EntityDatasetLoadError("sample_id_mismatch", "graph and label sample ids must match", graph.sample_dir)
    return EntityDatasetSample(
        sample_id=graph.sample_id,
        sample_dir=graph.sample_dir,
        graph=graph,
        labels=labels,
        model_input_paths=dict(graph.model_input_paths),
        label_paths={
            "part_class": (graph.sample_dir / "metadata" / "part_class_label.json").as_posix(),
            "face_segmentation": (graph.sample_dir / "labels" / "face_segmentation.json").as_posix(),
            "edge_segmentation": (graph.sample_dir / "labels" / "edge_segmentation.json").as_posix(),
            "mesh_size_field": (graph.sample_dir / "labels" / "mesh_size_field.json").as_posix(),
        },
    )
