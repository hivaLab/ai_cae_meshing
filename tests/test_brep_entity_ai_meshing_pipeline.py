from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.dataset.entity_loader import (
    EntityDatasetLoadError,
    load_entity_dataset_sample,
)
from ai_mesh_generator.amg.model.part_classifier import (
    predict_part_class,
    train_part_classifier,
)
from ai_mesh_generator.amg.model.segmentation import (
    BrepSegmentationModel,
    build_entity_graph_tensors,
    build_segmentation_targets,
)
from ai_mesh_generator.amg.model.size_field import (
    BrepSizeFieldModel,
    build_size_field_document,
    build_size_field_graph_tensors,
    build_size_field_targets,
)
from cad_dataset_factory.cdf.brep.entity_graph import (
    EntityBrepGraph,
    entity_graph_schema_document,
    validate_entity_brep_graph_structure,
    write_entity_brep_graph,
    write_entity_graph_schema,
    write_entity_signatures,
)
from cad_dataset_factory.cdf.labels.entity_labels import (
    EdgeSegmentationDocument,
    EdgeSegmentationLabel,
    EdgeSemanticLabel,
    EdgeSizeRecord,
    EntityQualityEvaluationDocument,
    EntityQualityRecord,
    EntityType,
    FaceSegmentationDocument,
    FaceSegmentationLabel,
    FaceSemanticLabel,
    GlobalMeshPolicy,
    MeshSizeFieldDocument,
    PartClass,
    PartClassLabelDocument,
    validate_entity_label_document,
    write_entity_label_json,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _workspace_tmp(name: str) -> Path:
    root = ROOT / "runs" / "pytest_tmp_local" / "brep_entity_ai_meshing" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _adj(rows: list[tuple[int, int]]) -> np.ndarray:
    return np.asarray(rows, dtype=np.int64) if rows else np.empty((0, 2), dtype=np.int64)


def _graph(scale: float = 1.0) -> EntityBrepGraph:
    face_features = np.asarray(
        [
            [100.0 * scale, 10.0, 10.0, 0.0, 5.0, 5.0, 0.0, 0.0, 0.0, 1.0, 4.0, 1.0],
            [20.0 * scale, 4.0, 5.0, 0.0, 2.0, 5.0, 0.0, 0.0, 0.0, 1.0, 4.0, 1.0],
        ],
        dtype=np.float64,
    )
    edge_features = np.asarray(
        [
            [1.0, 10.0 * scale, 10.0, 0.0, 0.0, 5.0, 0.0, 0.0, 2.0],
            [2.0, 2.0 * scale, 2.0, 2.0, 0.0, 5.0, 5.0, 0.0, 2.0],
            [1.0, 5.0 * scale, 5.0, 0.0, 0.0, 9.0, 5.0, 0.0, 2.0],
        ],
        dtype=np.float64,
    )
    arrays = {
        "node_type_ids": np.arange(1 + 2 + 3 + 4 + 4, dtype=np.int64),
        "part_features": np.asarray([[2.0, 3.0, 4.0, 4.0, 10.0 * scale, 10.0, 1.0]], dtype=np.float64),
        "face_features": face_features,
        "edge_features": edge_features,
        "coedge_features": np.asarray([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [1.0, 2.0, 0.0]], dtype=np.float64),
        "vertex_features": np.asarray([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [0.0, 10.0, 0.0]], dtype=np.float64),
    }
    edge_offset = 1 + arrays["face_features"].shape[0]
    adjacency = {
        "PART_HAS_FACE": _adj([(0, 1), (0, 2)]),
        "FACE_HAS_COEDGE": _adj([(1, 6), (1, 7), (2, 8), (2, 9)]),
        "COEDGE_HAS_EDGE": _adj([(6, edge_offset), (7, edge_offset + 1), (8, edge_offset + 1), (9, edge_offset + 2)]),
        "EDGE_HAS_VERTEX": _adj([(edge_offset, 10), (edge_offset + 1, 10), (edge_offset + 1, 11), (edge_offset + 2, 11)]),
        "COEDGE_NEXT": _adj([(6, 7), (7, 6), (8, 9), (9, 8)]),
        "COEDGE_PREV": _adj([(7, 6), (6, 7), (9, 8), (8, 9)]),
        "COEDGE_MATE": _adj([(7, 8), (8, 7)]),
        "FACE_ADJACENT_FACE": _adj([(1, 2), (2, 1)]),
    }
    entity_signatures = {
        "faces": [
            {
                "index": 0,
                "signature_id": "FACE_SIG_000001_BASE",
                "entity_type": "FACE",
                "fingerprint": {"entity_type": "FACE", "area_mm2": 100.0 * scale, "center_mm": [5.0, 5.0, 0.0], "bbox_mm": [10.0, 10.0, 0.0]},
                "debug_row_hash": "DEBUG_FACE_0001",
            },
            {
                "index": 1,
                "signature_id": "FACE_SIG_000002_HOLE",
                "entity_type": "FACE",
                "fingerprint": {"entity_type": "FACE", "area_mm2": 20.0 * scale, "center_mm": [2.0, 5.0, 0.0], "bbox_mm": [4.0, 5.0, 0.0]},
                "debug_row_hash": "DEBUG_FACE_0002",
            },
        ],
        "edges": [
            {
                "index": 0,
                "signature_id": "EDGE_SIG_000001_OUTER",
                "entity_type": "EDGE",
                "fingerprint": {"entity_type": "EDGE", "curve_type_id": 1, "length_mm": 10.0 * scale, "center_mm": [5.0, 0.0, 0.0], "bbox_mm": [10.0, 0.0, 0.0]},
                "debug_row_hash": "DEBUG_EDGE_0001",
            },
            {
                "index": 1,
                "signature_id": "EDGE_SIG_000002_HOLE",
                "entity_type": "EDGE",
                "fingerprint": {"entity_type": "EDGE", "curve_type_id": 2, "length_mm": 2.0 * scale, "center_mm": [5.0, 5.0, 0.0], "bbox_mm": [2.0, 2.0, 0.0]},
                "debug_row_hash": "DEBUG_EDGE_0002",
            },
            {
                "index": 2,
                "signature_id": "EDGE_SIG_000003_FREE",
                "entity_type": "EDGE",
                "fingerprint": {"entity_type": "EDGE", "curve_type_id": 1, "length_mm": 5.0 * scale, "center_mm": [9.0, 5.0, 0.0], "bbox_mm": [5.0, 0.0, 0.0]},
                "debug_row_hash": "DEBUG_EDGE_0003",
            },
        ],
    }
    graph = EntityBrepGraph(entity_graph_schema_document(), arrays, adjacency, entity_signatures)
    validate_entity_brep_graph_structure(graph)
    return graph


def _write_sample(root: Path, sample_id: str, part_class: PartClass, *, scale: float = 1.0, hard_fail: bool = False) -> Path:
    sample_dir = root / sample_id
    graph = _graph(scale)
    write_entity_brep_graph(sample_dir / "graph" / "brep_graph.npz", graph)
    write_entity_graph_schema(sample_dir / "graph" / "graph_schema.json", graph)
    write_entity_signatures(sample_dir / "graph" / "entity_signatures.json", graph)
    mesh_policy = GlobalMeshPolicy(h0_mm=2.0, h_min_mm=0.5, h_max_mm=4.0, growth_rate=1.25, quality_profile="AMG_QA_SHELL_V2")
    write_entity_label_json(
        sample_dir / "metadata" / "part_class_label.json",
        PartClassLabelDocument(sample_id=sample_id, part_class=part_class, source="test_fixture"),
    )
    write_entity_label_json(
        sample_dir / "labels" / "face_segmentation.json",
        FaceSegmentationDocument(
            sample_id=sample_id,
            labels=(
                FaceSegmentationLabel(face_signature_id="FACE_SIG_000001_BASE", semantic_label=FaceSemanticLabel.BASE_PANEL, instance_id="PANEL_0001"),
                FaceSegmentationLabel(face_signature_id="FACE_SIG_000002_HOLE", semantic_label=FaceSemanticLabel.HOLE_WALL, instance_id="HOLE_0001"),
            ),
        ),
    )
    write_entity_label_json(
        sample_dir / "labels" / "edge_segmentation.json",
        EdgeSegmentationDocument(
            sample_id=sample_id,
            labels=(
                EdgeSegmentationLabel(edge_signature_id="EDGE_SIG_000001_OUTER", semantic_label=EdgeSemanticLabel.OUTER_BOUNDARY),
                EdgeSegmentationLabel(edge_signature_id="EDGE_SIG_000002_HOLE", semantic_label=EdgeSemanticLabel.HOLE_BOUNDARY, instance_id="HOLE_0001"),
                EdgeSegmentationLabel(edge_signature_id="EDGE_SIG_000003_FREE", semantic_label=EdgeSemanticLabel.FREE_EDGE),
            ),
        ),
    )
    write_entity_label_json(
        sample_dir / "labels" / "mesh_size_field.json",
        MeshSizeFieldDocument(
            sample_id=sample_id,
            global_mesh=mesh_policy,
            edge_sizes=(EdgeSizeRecord(edge_signature_id="EDGE_SIG_000002_HOLE", target_size_mm=1.0, source="fixture"),),
            face_sizes=(),
        ),
    )
    quality = EntityQualityEvaluationDocument(
        sample_id=sample_id,
        evaluation_id="evaluation_000001",
        size_field_path="labels/mesh_size_field.json",
        entity_quality=(
            EntityQualityRecord(
                entity_signature_id="EDGE_SIG_000002_HOLE",
                entity_type=EntityType.EDGE,
                semantic_label="HOLE_BOUNDARY",
                candidate_target_size_mm=1.0 if not hard_fail else 3.5,
                candidate_neighbor_size_ratio_max=1.25,
                candidate_growth_rate=1.25,
                measured_quality_margin=-0.2 if not hard_fail else 2.0,
                measured_boundary_size_error=0.1 if not hard_fail else 1.2,
                hard_fail=hard_fail,
                near_fail=False,
                metric_available=True,
            ),
            EntityQualityRecord(
                entity_signature_id="FACE_SIG_000001_BASE",
                entity_type=EntityType.FACE,
                semantic_label="BASE_PANEL",
                candidate_target_size_mm=2.0,
                candidate_neighbor_size_ratio_max=1.25,
                candidate_growth_rate=1.25,
                measured_quality_margin=0.0,
                measured_boundary_size_error=0.0,
                hard_fail=False,
                near_fail=False,
                metric_available=True,
            ),
        ),
        global_quality_summary={"num_hard_failed_elements": int(hard_fail)},
    )
    write_entity_label_json(sample_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json", quality)
    return sample_dir


def test_new_entity_contract_schemas_validate_examples() -> None:
    for schema_name in (
        "AMG_SIZE_FIELD_SM_V2",
        "AMG_BREP_ENTITY_GRAPH_SM_V2",
        "CDF_PART_CLASS_LABEL_SM_V2",
        "CDF_FACE_SEGMENTATION_SM_V2",
        "CDF_EDGE_SEGMENTATION_SM_V2",
        "CDF_MESH_SIZE_FIELD_SM_V2",
        "CDF_ENTITY_QUALITY_EVALUATION_SM_V2",
    ):
        Draft202012Validator.check_schema(_load_schema(schema_name))
    sample = load_entity_dataset_sample(_write_sample(_workspace_tmp("contracts"), "sample_000001", PartClass.SM_FLAT_PANEL), require_quality=True)
    assert sample.graph.entity_signatures["edges"][0]["fingerprint"]["entity_type"] == "EDGE"
    assert "debug_row_hash" in sample.graph.entity_signatures["edges"][0]
    Draft202012Validator(_load_schema("CDF_MESH_SIZE_FIELD_SM_V2")).validate(sample.labels.mesh_size_field)
    Draft202012Validator(_load_schema("CDF_ENTITY_QUALITY_EVALUATION_SM_V2")).validate(sample.labels.quality_evaluations[0])


def test_entity_label_models_reject_duplicates_and_unavailable_reason() -> None:
    with pytest.raises(ValueError):
        FaceSegmentationDocument(
            sample_id="sample_000001",
            labels=(
                FaceSegmentationLabel(face_signature_id="FACE_A", semantic_label=FaceSemanticLabel.BASE_PANEL),
                FaceSegmentationLabel(face_signature_id="FACE_A", semantic_label=FaceSemanticLabel.BEND),
            ),
        )
    with pytest.raises(ValueError):
        EntityQualityRecord(
            entity_signature_id="EDGE_A",
            entity_type=EntityType.EDGE,
            candidate_target_size_mm=1.0,
            candidate_growth_rate=1.2,
            measured_quality_margin=0.0,
            hard_fail=False,
            near_fail=False,
            metric_available=False,
        )


def test_entity_dataset_loader_rejects_graph_target_leakage() -> None:
    sample_dir = _write_sample(_workspace_tmp("leakage"), "sample_000001", PartClass.SM_FLAT_PANEL)
    schema_path = sample_dir / "graph" / "graph_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["edge_feature_columns"].append("target_edge_length_mm")
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(EntityDatasetLoadError) as excinfo:
        load_entity_dataset_sample(sample_dir)
    assert excinfo.value.code == "graph_target_leakage"


def test_part_classifier_segmentation_and_direct_size_field_model() -> None:
    root = _workspace_tmp("models")
    samples = [
        load_entity_dataset_sample(_write_sample(root, "sample_000001", PartClass.SM_FLAT_PANEL, scale=1.0), require_quality=True),
        load_entity_dataset_sample(_write_sample(root, "sample_000002", PartClass.SM_FLAT_PANEL, scale=1.1), require_quality=True),
        load_entity_dataset_sample(_write_sample(root, "sample_000003", PartClass.SM_L_BRACKET, scale=2.0, hard_fail=True), require_quality=True),
        load_entity_dataset_sample(_write_sample(root, "sample_000004", PartClass.SM_L_BRACKET, scale=2.1, hard_fail=True), require_quality=True),
    ]
    classifier, classifier_result = train_part_classifier(samples, seed=42, n_estimators=20)
    assert classifier_result.sample_count == 4
    prediction = predict_part_class(classifier, samples[0], uncertainty_threshold=0.0)
    assert prediction.part_class in {"SM_FLAT_PANEL", "SM_L_BRACKET"}
    assert not prediction.uncertain

    tensors = build_entity_graph_tensors(samples[0])
    targets = build_segmentation_targets(samples[0])
    model = BrepSegmentationModel(tensors.face_features.shape[1], tensors.edge_features.shape[1], hidden_dim=16)
    output = model(tensors)
    assert output.face_logits.shape == (2, 8)
    assert output.edge_logits.shape == (3, 8)
    assert targets.face_labels.shape == (2,)
    assert targets.edge_labels.shape == (3,)

    size_tensors = build_size_field_graph_tensors(samples[0])
    size_targets = build_size_field_targets(samples[0])
    size_model = BrepSizeFieldModel(size_tensors.face_inputs.shape[1], size_tensors.edge_inputs.shape[1], hidden_dim=16)
    size_output = size_model(size_tensors)
    assert size_output.edge_log_h.shape == (3,)
    assert size_targets.edge_mask.tolist() == [False, True, False]
    document = build_size_field_document(samples[0], size_output, h0_mm=2.0, h_min_mm=0.5, h_max_mm=4.0, growth_rate=1.25)
    assert document["schema_version"] == "AMG_SIZE_FIELD_SM_V2"
    assert [row["edge_signature_id"] for row in document["edge_sizes"]] == ["EDGE_SIG_000002_HOLE"]
    Draft202012Validator(_load_schema("AMG_SIZE_FIELD_SM_V2")).validate(document)
