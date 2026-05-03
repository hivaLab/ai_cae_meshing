"""Load CDF dataset samples through AMG file contracts only."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

GRAPH_SCHEMA_VERSION = "AMG_BREP_GRAPH_SM_V1"
MANIFEST_SCHEMA_VERSION = "AMG_MANIFEST_SM_V1"
DATASET_INDEX_SCHEMA = "CDF_DATASET_INDEX_SM_V1"
CORE_GRAPH_ARRAYS = (
    "node_type_ids",
    "part_features",
    "face_features",
    "edge_features",
    "coedge_features",
    "vertex_features",
    "feature_candidate_features",
    "coedge_next",
    "coedge_prev",
    "coedge_mate",
)


class AmgDatasetLoadError(ValueError):
    """Raised when an AMG dataset file contract cannot be loaded safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class BrepGraphInput:
    sample_id: str
    sample_dir: Path
    graph_npz_path: Path
    graph_schema_path: Path
    graph_schema: dict[str, Any]
    arrays: dict[str, np.ndarray]
    adjacency: dict[str, np.ndarray]
    model_input_paths: dict[str, str]


@dataclass(frozen=True)
class AmgManifestLabel:
    sample_id: str
    sample_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]
    status: str
    feature_count: int


@dataclass(frozen=True)
class AmgDatasetSample:
    sample_id: str
    sample_dir: Path
    graph: BrepGraphInput
    manifest: AmgManifestLabel
    model_input_paths: dict[str, str]
    label_paths: dict[str, str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema(name: str) -> dict[str, Any]:
    return _read_json(_repo_root() / "contracts" / f"{name}.schema.json", code="schema_read_failed")


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgDatasetLoadError(code, f"could not read JSON file: {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgDatasetLoadError("json_parse_failed", f"could not parse JSON file: {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgDatasetLoadError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _json_object(value: Mapping[str, Any], *, code: str, path: Path | None = None) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AmgDatasetLoadError(code, "document must be JSON-compatible", path) from exc
    if not isinstance(normalized, dict):
        raise AmgDatasetLoadError(code, "document must be a JSON object", path)
    return normalized


def _validate_schema(document: dict[str, Any], schema_name: str, *, code: str, path: Path) -> None:
    validator = Draft202012Validator(_schema(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise AmgDatasetLoadError(code, f"{schema_name} {location}: {first.message}", path)


def _require_file(path: Path, *, code: str) -> None:
    if not path.is_file():
        raise AmgDatasetLoadError(code, f"required file does not exist: {path}", path)


def _sample_dir(path: str | Path) -> Path:
    sample_dir = Path(path)
    if not sample_dir.is_dir():
        raise AmgDatasetLoadError("missing_sample_dir", f"sample directory does not exist: {sample_dir}", sample_dir)
    return sample_dir


def _load_graph_schema(path: Path) -> dict[str, Any]:
    _require_file(path, code="missing_graph_schema")
    graph_schema = _read_json(path, code="graph_schema_read_failed")
    _validate_schema(graph_schema, GRAPH_SCHEMA_VERSION, code="graph_schema_invalid", path=path)
    if graph_schema.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise AmgDatasetLoadError("graph_schema_invalid", f"schema_version must be {GRAPH_SCHEMA_VERSION}", path)
    return graph_schema


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    _require_file(path, code="missing_brep_graph")
    try:
        loaded = np.load(path, allow_pickle=False)
    except OSError as exc:
        raise AmgDatasetLoadError("brep_graph_read_failed", f"could not read graph npz: {path}", path) from exc
    with loaded:
        return {key: np.array(loaded[key], copy=True) for key in loaded.files}


def _validate_graph_arrays(arrays: dict[str, np.ndarray], graph_schema: Mapping[str, Any], path: Path) -> dict[str, np.ndarray]:
    for key in CORE_GRAPH_ARRAYS:
        if key not in arrays:
            raise AmgDatasetLoadError("missing_graph_array", f"missing graph array: {key}", path)

    if arrays["node_type_ids"].ndim != 1 or not np.issubdtype(arrays["node_type_ids"].dtype, np.integer):
        raise AmgDatasetLoadError("malformed_graph_array", "node_type_ids must be a 1D integer array", path)
    if arrays["part_features"].ndim != 2 or arrays["part_features"].shape[0] != 1:
        raise AmgDatasetLoadError("malformed_graph_array", "part_features must have exactly one row", path)

    candidate_rows = arrays["feature_candidate_features"]
    expected_columns = len(graph_schema["feature_candidate_columns"])
    if candidate_rows.ndim != 2 or candidate_rows.shape[1] != expected_columns:
        raise AmgDatasetLoadError(
            "malformed_graph_array",
            "feature_candidate_features must match graph_schema feature_candidate_columns",
            path,
        )

    for key in ("feature_candidate_ids", "feature_candidate_metadata_json"):
        if key in arrays and arrays[key].shape[0] != candidate_rows.shape[0]:
            raise AmgDatasetLoadError("malformed_candidate_metadata", f"{key} row count must match feature candidates", path)

    adjacency: dict[str, np.ndarray] = {}
    for edge_type in graph_schema["edge_types"]:
        key = f"adj_{edge_type}"
        if key not in arrays:
            raise AmgDatasetLoadError("missing_adjacency_array", f"missing adjacency array: {key}", path)
        adjacency_array = arrays[key]
        if adjacency_array.ndim != 2 or adjacency_array.shape[1] != 2 or not np.issubdtype(adjacency_array.dtype, np.integer):
            raise AmgDatasetLoadError("malformed_adjacency_array", f"{key} must be an integer Nx2 array", path)
        adjacency[edge_type] = adjacency_array

    return adjacency


def load_brep_graph_input(sample_dir: str | Path) -> BrepGraphInput:
    """Load the graph model input for one CDF sample directory."""

    sample_path = _sample_dir(sample_dir)
    graph_npz_path = sample_path / "graph" / "brep_graph.npz"
    graph_schema_path = sample_path / "graph" / "graph_schema.json"
    graph_schema = _load_graph_schema(graph_schema_path)
    arrays = _load_npz(graph_npz_path)
    adjacency = _validate_graph_arrays(arrays, graph_schema, graph_npz_path)
    return BrepGraphInput(
        sample_id=sample_path.name,
        sample_dir=sample_path,
        graph_npz_path=graph_npz_path,
        graph_schema_path=graph_schema_path,
        graph_schema=graph_schema,
        arrays=arrays,
        adjacency=adjacency,
        model_input_paths={
            "brep_graph": graph_npz_path.as_posix(),
            "graph_schema": graph_schema_path.as_posix(),
        },
    )


def load_manifest_label(sample_dir: str | Path) -> AmgManifestLabel:
    """Load the AMG manifest supervision label for one sample."""

    sample_path = _sample_dir(sample_dir)
    manifest_path = sample_path / "labels" / "amg_manifest.json"
    _require_file(manifest_path, code="missing_manifest")
    manifest = _read_json(manifest_path, code="manifest_read_failed")
    _validate_schema(manifest, MANIFEST_SCHEMA_VERSION, code="manifest_schema_invalid", path=manifest_path)
    return AmgManifestLabel(
        sample_id=sample_path.name,
        sample_dir=sample_path,
        manifest_path=manifest_path,
        manifest=_json_object(manifest, code="manifest_not_json_compatible", path=manifest_path),
        status=str(manifest["status"]),
        feature_count=len(manifest.get("features", [])),
    )


def load_amg_dataset_sample(sample_dir: str | Path) -> AmgDatasetSample:
    """Load graph inputs and manifest labels for one accepted CDF sample."""

    graph = load_brep_graph_input(sample_dir)
    manifest = load_manifest_label(sample_dir)
    if graph.sample_id != manifest.sample_id:
        raise AmgDatasetLoadError("sample_id_mismatch", "graph and manifest sample ids must match", graph.sample_dir)
    return AmgDatasetSample(
        sample_id=graph.sample_id,
        sample_dir=graph.sample_dir,
        graph=graph,
        manifest=manifest,
        model_input_paths=dict(graph.model_input_paths),
        label_paths={"amg_manifest": manifest.manifest_path.as_posix()},
    )


def load_dataset_index(dataset_root: str | Path) -> dict[str, Any]:
    """Load the lightweight CDF dataset index contract."""

    root = Path(dataset_root)
    index_path = root / "dataset_index.json"
    _require_file(index_path, code="missing_dataset_index")
    index = _read_json(index_path, code="dataset_index_read_failed")
    if index.get("schema") != DATASET_INDEX_SCHEMA:
        raise AmgDatasetLoadError("dataset_index_schema_invalid", f"schema must be {DATASET_INDEX_SCHEMA}", index_path)
    if not isinstance(index.get("accepted_samples"), list):
        raise AmgDatasetLoadError("dataset_index_schema_invalid", "accepted_samples must be a list", index_path)
    if not isinstance(index.get("rejected_samples", []), list):
        raise AmgDatasetLoadError("dataset_index_schema_invalid", "rejected_samples must be a list", index_path)
    return _json_object(index, code="dataset_index_not_json_compatible", path=index_path)


def _accepted_sample_records(index: Mapping[str, Any], dataset_root: Path) -> dict[str, Path]:
    records: dict[str, Path] = {}
    for item in index["accepted_samples"]:
        if isinstance(item, str):
            sample_id = item
            sample_dir = dataset_root / "samples" / sample_id
        elif isinstance(item, Mapping):
            sample_id = item.get("sample_id")
            if not isinstance(sample_id, str) or not sample_id:
                raise AmgDatasetLoadError("dataset_index_schema_invalid", "accepted sample records require sample_id", dataset_root)
            sample_dir_value = item.get("sample_dir", f"samples/{sample_id}")
            if not isinstance(sample_dir_value, str):
                raise AmgDatasetLoadError("dataset_index_schema_invalid", "sample_dir must be a string", dataset_root)
            sample_dir = Path(sample_dir_value)
            sample_dir = sample_dir if sample_dir.is_absolute() else dataset_root / sample_dir
        else:
            raise AmgDatasetLoadError("dataset_index_schema_invalid", "accepted sample records must be strings or objects", dataset_root)
        if sample_id in records:
            raise AmgDatasetLoadError("duplicate_sample_id", "accepted sample ids must be unique", dataset_root)
        records[sample_id] = sample_dir
    return records


def _split_sample_ids(dataset_root: Path, split: str | None) -> list[str] | None:
    if split is None:
        return None
    if not isinstance(split, str) or not split:
        raise AmgDatasetLoadError("malformed_split", "split must be a non-empty string", dataset_root)
    split_path = dataset_root / "splits" / f"{split}.txt"
    _require_file(split_path, code="missing_split_file")
    lines = split_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def iter_amg_dataset_samples(dataset_root: str | Path, split: str | None = None) -> Iterator[AmgDatasetSample]:
    """Iterate accepted AMG dataset samples, optionally restricted by a split file."""

    root = Path(dataset_root)
    index = load_dataset_index(root)
    accepted = _accepted_sample_records(index, root)
    split_ids = _split_sample_ids(root, split)
    sample_ids = list(accepted) if split_ids is None else split_ids
    for sample_id in sample_ids:
        if sample_id not in accepted:
            raise AmgDatasetLoadError("split_sample_not_in_index", f"split sample is not accepted: {sample_id}", root)
        yield load_amg_dataset_sample(accepted[sample_id])
