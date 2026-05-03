from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ai_mesh_generator.amg.dataset import (
    AmgDatasetLoadError,
    iter_amg_dataset_samples,
    load_amg_dataset_sample,
    load_brep_graph_input,
    load_dataset_index,
    load_manifest_label,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_dataset_loader"
FEATURE_COLUMNS = [
    "feature_type_id",
    "role_id",
    "size_1_over_Lref",
    "size_2_over_Lref",
    "radius_over_Lref",
    "width_over_Lref",
    "length_over_Lref",
    "center_x_over_Lref",
    "center_y_over_Lref",
    "center_z_over_Lref",
    "distance_to_outer_boundary_over_Lref",
    "distance_to_nearest_feature_over_Lref",
    "clearance_ratio",
    "expected_action_mask",
]
EDGE_TYPES = [
    "PART_HAS_FACE",
    "FACE_HAS_COEDGE",
    "COEDGE_HAS_EDGE",
    "EDGE_HAS_VERTEX",
    "COEDGE_NEXT",
    "COEDGE_PREV",
    "COEDGE_MATE",
    "FACE_ADJACENT_FACE",
    "FEATURE_CONTAINS_FACE",
    "FEATURE_CONTAINS_EDGE",
]


def _graph_schema() -> dict:
    return {
        "schema_version": "AMG_BREP_GRAPH_SM_V1",
        "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
        "edge_types": EDGE_TYPES,
        "feature_candidate_columns": FEATURE_COLUMNS,
    }


def _manifest() -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": "SMT_SAMPLE",
            "part_class": "SM_FLAT_PANEL",
            "idealization": "midsurface_shell",
            "thickness_mm": 1.2,
            "element_type": "quad_dominant_shell",
            "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
        },
        "global_mesh": {
            "h0_mm": 4.0,
            "h_min_mm": 1.2,
            "h_max_mm": 7.2,
            "growth_rate_max": 1.3,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_graph_npz(sample_dir: Path, *, rows: int = 1, metadata_rows: int | None = None, candidate_id_rows: int | None = None, columns: int | None = None) -> None:
    graph_dir = sample_dir / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    column_count = len(FEATURE_COLUMNS) if columns is None else columns
    metadata_count = rows if metadata_rows is None else metadata_rows
    candidate_id_count = rows if candidate_id_rows is None else candidate_id_rows
    adjacency = {f"adj_{edge_type}": np.empty((0, 2), dtype=np.int64) for edge_type in EDGE_TYPES}
    np.savez(
        graph_dir / "brep_graph.npz",
        node_type_ids=np.asarray([0], dtype=np.int64),
        part_features=np.asarray([[0.0, 0.0, 0.0, 0.0, 100.0, 64.0, 1.2]], dtype=np.float64),
        face_features=np.empty((0, 11), dtype=np.float64),
        edge_features=np.empty((0, 10), dtype=np.float64),
        coedge_features=np.empty((0, 4), dtype=np.float64),
        vertex_features=np.empty((0, 3), dtype=np.float64),
        feature_candidate_features=np.zeros((rows, column_count), dtype=np.float64),
        feature_candidate_ids=np.asarray([f"FEATURE_{index:04d}" for index in range(candidate_id_count)]),
        feature_candidate_metadata_json=np.asarray(
            [json.dumps({"candidate_id": f"FEATURE_{index:04d}"}) for index in range(metadata_count)]
        ),
        coedge_next=np.empty((0, 2), dtype=np.int64),
        coedge_prev=np.empty((0, 2), dtype=np.int64),
        coedge_mate=np.empty((0, 2), dtype=np.int64),
        **adjacency,
    )


def _write_sample(dataset_root: Path, sample_id: str = "sample_000001") -> Path:
    sample_dir = dataset_root / "samples" / sample_id
    _write_json(sample_dir / "graph" / "graph_schema.json", _graph_schema())
    _write_graph_npz(sample_dir)
    _write_json(sample_dir / "labels" / "amg_manifest.json", _manifest())
    (sample_dir / "cad").mkdir(parents=True, exist_ok=True)
    (sample_dir / "cad" / "reference_midsurface.step").write_text("debug-only reference\n", encoding="utf-8")
    return sample_dir


def _write_dataset_index(dataset_root: Path, sample_ids: list[str]) -> None:
    _write_json(
        dataset_root / "dataset_index.json",
        {
            "schema": "CDF_DATASET_INDEX_SM_V1",
            "num_accepted": len(sample_ids),
            "num_rejected": 0,
            "accepted_samples": [
                {
                    "sample_id": sample_id,
                    "sample_dir": f"samples/{sample_id}",
                    "manifest": f"samples/{sample_id}/labels/amg_manifest.json",
                    "acceptance_report": f"samples/{sample_id}/reports/sample_acceptance.json",
                }
                for sample_id in sample_ids
            ],
            "rejected_samples": [],
        },
    )


def test_valid_sample_loads_graph_and_manifest_contracts() -> None:
    dataset_root = RUNS / "valid_sample"
    sample_dir = _write_sample(dataset_root)

    sample = load_amg_dataset_sample(sample_dir)

    assert sample.sample_id == "sample_000001"
    assert sample.graph.graph_schema["schema_version"] == "AMG_BREP_GRAPH_SM_V1"
    assert sample.manifest.manifest["schema_version"] == "AMG_MANIFEST_SM_V1"
    assert sample.graph.arrays["feature_candidate_features"].shape == (1, len(FEATURE_COLUMNS))
    assert set(sample.graph.adjacency) == set(EDGE_TYPES)
    assert sample.model_input_paths == sample.graph.model_input_paths
    serialized_paths = json.dumps(sample.model_input_paths) + json.dumps(sample.label_paths)
    assert "reference_midsurface" not in serialized_paths


def test_manifest_label_loader_reports_status_and_feature_count() -> None:
    sample_dir = _write_sample(RUNS / "manifest_label")

    label = load_manifest_label(sample_dir)

    assert label.status == "VALID"
    assert label.feature_count == 0


def test_feature_candidate_column_mismatch_raises_structured_error() -> None:
    sample_dir = RUNS / "bad_columns" / "samples" / "sample_000001"
    _write_json(sample_dir / "graph" / "graph_schema.json", _graph_schema())
    _write_graph_npz(sample_dir, columns=len(FEATURE_COLUMNS) - 1)

    with pytest.raises(AmgDatasetLoadError) as exc_info:
        load_brep_graph_input(sample_dir)

    assert exc_info.value.code == "malformed_graph_array"


def test_missing_required_files_raise_structured_errors() -> None:
    missing_graph_schema = RUNS / "missing_graph_schema" / "samples" / "sample_000001"
    missing_graph_schema.mkdir(parents=True, exist_ok=True)
    with pytest.raises(AmgDatasetLoadError) as graph_schema_exc:
        load_brep_graph_input(missing_graph_schema)
    assert graph_schema_exc.value.code == "missing_graph_schema"

    missing_brep_graph = RUNS / "missing_brep_graph" / "samples" / "sample_000001"
    _write_json(missing_brep_graph / "graph" / "graph_schema.json", _graph_schema())
    with pytest.raises(AmgDatasetLoadError) as graph_exc:
        load_brep_graph_input(missing_brep_graph)
    assert graph_exc.value.code == "missing_brep_graph"

    missing_manifest = RUNS / "missing_manifest" / "samples" / "sample_000001"
    missing_manifest.mkdir(parents=True, exist_ok=True)
    with pytest.raises(AmgDatasetLoadError) as manifest_exc:
        load_manifest_label(missing_manifest)
    assert manifest_exc.value.code == "missing_manifest"


def test_malformed_manifest_schema_raises_structured_error() -> None:
    sample_dir = RUNS / "bad_manifest" / "samples" / "sample_000001"
    _write_json(sample_dir / "labels" / "amg_manifest.json", {"schema_version": "AMG_MANIFEST_SM_V1"})

    with pytest.raises(AmgDatasetLoadError) as exc_info:
        load_manifest_label(sample_dir)

    assert exc_info.value.code == "manifest_schema_invalid"


def test_candidate_metadata_and_id_row_mismatch_raise() -> None:
    metadata_bad = RUNS / "bad_metadata" / "samples" / "sample_000001"
    _write_json(metadata_bad / "graph" / "graph_schema.json", _graph_schema())
    _write_graph_npz(metadata_bad, rows=1, metadata_rows=0)
    with pytest.raises(AmgDatasetLoadError) as metadata_exc:
        load_brep_graph_input(metadata_bad)
    assert metadata_exc.value.code == "malformed_candidate_metadata"

    ids_bad = RUNS / "bad_ids" / "samples" / "sample_000001"
    _write_json(ids_bad / "graph" / "graph_schema.json", _graph_schema())
    _write_graph_npz(ids_bad, rows=1, candidate_id_rows=0)
    with pytest.raises(AmgDatasetLoadError) as ids_exc:
        load_brep_graph_input(ids_bad)
    assert ids_exc.value.code == "malformed_candidate_metadata"


def test_dataset_index_iteration_loads_only_accepted_samples() -> None:
    dataset_root = RUNS / "dataset_index"
    _write_sample(dataset_root, "sample_000001")
    _write_sample(dataset_root, "sample_000002")
    _write_dataset_index(dataset_root, ["sample_000001", "sample_000002"])

    index = load_dataset_index(dataset_root)
    samples = list(iter_amg_dataset_samples(dataset_root))

    assert index["schema"] == "CDF_DATASET_INDEX_SM_V1"
    assert [sample.sample_id for sample in samples] == ["sample_000001", "sample_000002"]


def test_split_filtering_loads_only_listed_sample_ids() -> None:
    dataset_root = RUNS / "split_filter"
    _write_sample(dataset_root, "sample_000001")
    _write_sample(dataset_root, "sample_000002")
    _write_dataset_index(dataset_root, ["sample_000001", "sample_000002"])
    split_path = dataset_root / "splits" / "train.txt"
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text("# comment\nsample_000002\n", encoding="utf-8")

    samples = list(iter_amg_dataset_samples(dataset_root, split="train"))

    assert [sample.sample_id for sample in samples] == ["sample_000002"]


def test_loader_source_does_not_import_cdf_package() -> None:
    loader_source = (ROOT / "ai_mesh_generator" / "amg" / "dataset" / "loader.py").read_text(encoding="utf-8")

    assert "cad_dataset_factory" not in loader_source
