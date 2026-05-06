"""Primary CDF v2 entity-dataset publisher.

This module is the replacement for the old feature-manifest dataset path.  It writes
CAD-native graph inputs and separate part/face/edge/size labels.
"""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.brep import (
    EntityBrepGraph,
    extract_entity_brep_graph,
    write_entity_brep_graph,
    write_entity_graph_schema,
    write_entity_signatures,
)
from cad_dataset_factory.cdf.cadgen.bent_part import BentPartSpec, build_bent_part, write_bent_part_outputs
from cad_dataset_factory.cdf.cadgen.flat_panel import FlatPanelFeatureSpec, FlatPanelSpec, build_flat_panel_part, write_flat_panel_outputs
from cad_dataset_factory.cdf.domain import FeatureRole, FeatureType, PartClass
from cad_dataset_factory.cdf.labels import (
    EdgeSegmentationDocument,
    EdgeSegmentationLabel,
    EdgeSemanticLabel,
    EdgeSizeRecord,
    FaceSegmentationDocument,
    FaceSegmentationLabel,
    FaceSemanticLabel,
    GlobalMeshPolicy,
    MeshSizeFieldDocument,
    PartClassLabelDocument,
    write_entity_label_json,
)

PART_CASES = (
    "flat_hole",
    "flat_slot",
    "flat_cutout",
    "flat_combo",
    "single_flange",
    "l_bracket",
    "u_channel",
    "hat_channel",
)


class CdfEntityPipelineError(ValueError):
    """Raised when the v2 entity dataset pipeline cannot proceed."""

    def __init__(self, code: str, message: str, sample_id: str | None = None) -> None:
        self.code = code
        self.sample_id = sample_id
        prefix = code if sample_id is None else f"{code} [{sample_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class EntityGenerateResult:
    status: str
    dataset_root: Path
    requested_count: int
    generated_count: int
    blocked_count: int
    exit_code: int
    reason: str | None = None


@dataclass(frozen=True)
class EntityValidateResult:
    status: str
    dataset_root: Path
    sample_count: int
    error_count: int
    errors: tuple[str, ...]
    exit_code: int


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema(schema_version: str) -> dict[str, Any]:
    return json.loads((_repo_root() / "contracts" / f"{schema_version}.schema.json").read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise CdfEntityPipelineError("json_not_object", f"JSON file must contain an object: {path}")
    return loaded


def _validate_document(path: Path, schema_version: str) -> None:
    document = _read_json(path)
    if document.get("schema_version") != schema_version:
        raise CdfEntityPipelineError("schema_version_mismatch", f"{path} must use {schema_version}")
    errors = sorted(Draft202012Validator(_schema(schema_version)).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise CdfEntityPipelineError("schema_validation_failed", f"{path} {location}: {first.message}")


def _flat_spec(sample_id: str, case: str, rng: random.Random) -> FlatPanelSpec:
    width = 120.0 + rng.randint(0, 5) * 8.0
    height = 80.0 + rng.randint(0, 5) * 6.0
    thickness = 1.0 + rng.randint(0, 3) * 0.25
    features: list[FlatPanelFeatureSpec] = []
    if case in {"flat_hole", "flat_combo"}:
        features.append(
            FlatPanelFeatureSpec(
                feature_id="HOLE_UNKNOWN_0001",
                type=FeatureType.HOLE,
                role=FeatureRole.UNKNOWN,
                center_uv_mm=(width * 0.35, height * 0.5),
                radius_mm=4.0,
            )
        )
    if case in {"flat_slot", "flat_combo"}:
        features.append(
            FlatPanelFeatureSpec(
                feature_id="SLOT_PASSAGE_0001",
                type=FeatureType.SLOT,
                role=FeatureRole.PASSAGE,
                center_uv_mm=(width * 0.65, height * 0.55),
                width_mm=7.0,
                length_mm=24.0,
            )
        )
    if case in {"flat_cutout", "flat_combo"}:
        features.append(
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_RELIEF_0001",
                type=FeatureType.CUTOUT,
                role=FeatureRole.RELIEF,
                center_uv_mm=(width * 0.5, height * 0.28),
                width_mm=18.0,
                height_mm=12.0,
            )
        )
    return FlatPanelSpec(
        sample_id=sample_id,
        part_name=f"{case.upper()}_{sample_id}",
        width_mm=width,
        height_mm=height,
        thickness_mm=thickness,
        features=features,
    )


def _bent_spec(sample_id: str, case: str, rng: random.Random) -> BentPartSpec:
    part_class = {
        "single_flange": PartClass.SM_SINGLE_FLANGE,
        "l_bracket": PartClass.SM_L_BRACKET,
        "u_channel": PartClass.SM_U_CHANNEL,
        "hat_channel": PartClass.SM_HAT_CHANNEL,
    }[case]
    thickness = 1.0 + rng.randint(0, 3) * 0.25
    return BentPartSpec(
        sample_id=sample_id,
        part_name=f"{case.upper()}_{sample_id}",
        part_class=part_class,
        length_mm=120.0 + rng.randint(0, 4) * 10.0,
        web_width_mm=60.0 + rng.randint(0, 4) * 8.0,
        flange_width_mm=30.0 + rng.randint(0, 4) * 5.0,
        side_wall_width_mm=28.0 + rng.randint(0, 3) * 4.0,
        thickness_mm=thickness,
        inner_radius_mm=max(0.75, thickness * 0.75),
        bend_angle_deg=90.0,
    )


def _label_for_face(graph: EntityBrepGraph, face_index: int, part_class: str) -> FaceSemanticLabel:
    face = graph.arrays["face_features"][face_index]
    area = float(face[0])
    max_area = float(np.max(graph.arrays["face_features"][:, 0])) if graph.arrays["face_features"].size else area
    normal_z = abs(float(face[9])) if face.shape[0] > 9 else 0.0
    if part_class == "SM_FLAT_PANEL":
        if area >= 0.5 * max_area and normal_z > 0.7:
            return FaceSemanticLabel.BASE_PANEL
        return FaceSemanticLabel.SIDE_WALL
    if normal_z < 0.25:
        return FaceSemanticLabel.FLANGE
    if 0.25 <= normal_z <= 0.85:
        return FaceSemanticLabel.BEND
    return FaceSemanticLabel.BASE_PANEL


def _label_for_edge(graph: EntityBrepGraph, edge_index: int, part_class: str, case: str) -> EdgeSemanticLabel:
    edge = graph.arrays["edge_features"][edge_index]
    curve_type = int(round(float(edge[0])))
    length = float(edge[1])
    if curve_type in {2, 3}:
        if "slot" in case:
            return EdgeSemanticLabel.SLOT_BOUNDARY
        return EdgeSemanticLabel.HOLE_BOUNDARY
    if "cutout" in case and length < 25.0:
        return EdgeSemanticLabel.CUTOUT_BOUNDARY
    if part_class != "SM_FLAT_PANEL" and length > 20.0:
        return EdgeSemanticLabel.BEND_EDGE
    return EdgeSemanticLabel.OUTER_BOUNDARY if edge_index % 2 == 0 else EdgeSemanticLabel.FREE_EDGE


def _target_size_for_edge(label: EdgeSemanticLabel, mesh: GlobalMeshPolicy) -> float:
    if label in {EdgeSemanticLabel.HOLE_BOUNDARY, EdgeSemanticLabel.SLOT_BOUNDARY, EdgeSemanticLabel.CUTOUT_BOUNDARY}:
        return max(mesh.h_min_mm, mesh.h0_mm * 0.35)
    if label == EdgeSemanticLabel.BEND_EDGE:
        return max(mesh.h_min_mm, mesh.h0_mm * 0.45)
    return mesh.h0_mm


def _write_entity_labels(sample_dir: Path, sample_id: str, graph: EntityBrepGraph, part_class: str, case: str) -> None:
    mesh = GlobalMeshPolicy(h0_mm=3.0, h_min_mm=0.5, h_max_mm=8.0, growth_rate=1.25, quality_profile="AMG_QA_SHELL_V2")
    write_entity_label_json(
        sample_dir / "metadata" / "part_class_label.json",
        PartClassLabelDocument(sample_id=sample_id, part_class=part_class, source="cdf_entity_generator_v2"),
    )
    face_labels = tuple(
        FaceSegmentationLabel(
            face_signature_id=record["signature_id"],
            semantic_label=_label_for_face(graph, int(record["index"]), part_class),
        )
        for record in graph.entity_signatures["faces"]
    )
    edge_items: list[EdgeSegmentationLabel] = []
    size_items: list[EdgeSizeRecord] = []
    for record in graph.entity_signatures["edges"]:
        semantic = _label_for_edge(graph, int(record["index"]), part_class, case)
        edge_items.append(EdgeSegmentationLabel(edge_signature_id=record["signature_id"], semantic_label=semantic))
        size_items.append(
            EdgeSizeRecord(
                edge_signature_id=record["signature_id"],
                target_size_mm=_target_size_for_edge(semantic, mesh),
                source="cdf_entity_generator_v2",
            )
        )
    write_entity_label_json(sample_dir / "labels" / "face_segmentation.json", FaceSegmentationDocument(sample_id=sample_id, labels=face_labels))
    write_entity_label_json(sample_dir / "labels" / "edge_segmentation.json", EdgeSegmentationDocument(sample_id=sample_id, labels=tuple(edge_items)))
    write_entity_label_json(
        sample_dir / "labels" / "mesh_size_field.json",
        MeshSizeFieldDocument(sample_id=sample_id, global_mesh=mesh, edge_sizes=tuple(size_items), face_sizes=()),
    )


def _generate_one(sample_dir: Path, sample_id: str, case: str, rng: random.Random) -> dict[str, Any]:
    if case.startswith("flat"):
        generated = build_flat_panel_part(_flat_spec(sample_id, case, rng))
        write_flat_panel_outputs(sample_dir, generated)
        part_class = "SM_FLAT_PANEL"
    else:
        generated = build_bent_part(_bent_spec(sample_id, case, rng))
        write_bent_part_outputs(sample_dir, generated)
        part_class = str(generated.spec.part_class.value)
    graph = extract_entity_brep_graph(sample_dir / "cad" / "input.step")
    write_entity_brep_graph(sample_dir / "graph" / "brep_graph.npz", graph)
    write_entity_graph_schema(sample_dir / "graph" / "graph_schema.json", graph)
    write_entity_signatures(sample_dir / "graph" / "entity_signatures.json", graph)
    _write_entity_labels(sample_dir, sample_id, graph, part_class, case)
    return {
        "sample_id": sample_id,
        "profile_case": case,
        "part_class": part_class,
        "path": f"samples/{sample_id}",
    }


def generate_entity_dataset(out_dir: str | Path, *, count: int, seed: int = 1, profile: str = "sm_entity_v2_compact") -> EntityGenerateResult:
    if count <= 0:
        raise CdfEntityPipelineError("invalid_count", "count must be positive")
    if profile != "sm_entity_v2_compact":
        raise CdfEntityPipelineError("unsupported_profile", "only sm_entity_v2_compact is supported in the v2 primary path")
    root = Path(out_dir)
    if root.exists():
        shutil.rmtree(root)
    (root / "samples").mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for index in range(count):
        sample_id = f"sample_{index + 1:06d}"
        case = PART_CASES[index % len(PART_CASES)]
        records.append(_generate_one(root / "samples" / sample_id, sample_id, case, rng))
    dataset_index = {
        "schema": "CDF_ENTITY_DATASET_INDEX_SM_V2",
        "profile": profile,
        "seed": seed,
        "sample_count": len(records),
        "samples": records,
    }
    _write_json(root / "dataset_index.json", dataset_index)
    return EntityGenerateResult("SUCCESS", root, count, len(records), 0, 0)


def validate_entity_dataset(dataset_root: str | Path, *, require_quality: bool = False) -> EntityValidateResult:
    root = Path(dataset_root)
    errors: list[str] = []
    samples_root = root / "samples"
    sample_dirs = sorted(path for path in samples_root.glob("sample_*") if path.is_dir())
    if not sample_dirs:
        errors.append("missing_samples")
    for sample_dir in sample_dirs:
        try:
            graph_schema = _read_json(sample_dir / "graph" / "graph_schema.json")
            if graph_schema.get("schema_version") != "AMG_BREP_ENTITY_GRAPH_SM_V2":
                raise CdfEntityPipelineError("graph_schema_invalid", "graph_schema.json must use AMG_BREP_ENTITY_GRAPH_SM_V2")
            graph_arrays = np.load(sample_dir / "graph" / "brep_graph.npz", allow_pickle=False)
            with graph_arrays:
                for key in ("part_features", "face_features", "edge_features", "coedge_features", "vertex_features"):
                    if key not in graph_arrays.files:
                        raise CdfEntityPipelineError("missing_graph_array", f"missing graph array: {key}")
                    if graph_arrays[key].ndim != 2:
                        raise CdfEntityPipelineError("malformed_graph_array", f"{key} must be 2D")
            signatures = _read_json(sample_dir / "graph" / "entity_signatures.json")
            if "faces" not in signatures or "edges" not in signatures:
                raise CdfEntityPipelineError("malformed_entity_signatures", "entity_signatures.json requires faces and edges")
            _validate_document(sample_dir / "metadata" / "part_class_label.json", "CDF_PART_CLASS_LABEL_SM_V2")
            _validate_document(sample_dir / "labels" / "face_segmentation.json", "CDF_FACE_SEGMENTATION_SM_V2")
            _validate_document(sample_dir / "labels" / "edge_segmentation.json", "CDF_EDGE_SEGMENTATION_SM_V2")
            _validate_document(sample_dir / "labels" / "mesh_size_field.json", "CDF_MESH_SIZE_FIELD_SM_V2")
            quality_paths = sorted((sample_dir / "quality_evaluations").glob("*/entity_quality_labels.json"))
            if require_quality and not quality_paths:
                raise CdfEntityPipelineError("missing_entity_quality", "quality evaluation is required")
            for quality_path in quality_paths:
                _validate_document(quality_path, "CDF_ENTITY_QUALITY_EVALUATION_SM_V2")
                if require_quality:
                    quality_doc = _read_json(quality_path)
                    rows = quality_doc.get("entity_quality", [])
                    if not rows:
                        raise CdfEntityPipelineError("empty_entity_quality", "entity quality rows are required")
                    for row in rows:
                        if not row.get("metric_available"):
                            raise CdfEntityPipelineError("entity_quality_metric_unavailable", f"{quality_path} contains unavailable local metrics")
                        if row.get("hard_fail"):
                            raise CdfEntityPipelineError("entity_quality_hard_fail", f"{quality_path} contains hard-fail entity quality rows")
                    summary = quality_doc.get("global_quality_summary", {})
                    if isinstance(summary, dict) and summary.get("num_hard_failed_elements", 0) != 0:
                        raise CdfEntityPipelineError("global_quality_hard_fail", f"{quality_path} reports hard failed elements")
        except Exception as exc:  # noqa: BLE001 - validation should collect every failing sample.
            errors.append(f"{sample_dir.name}: {exc}")
    status = "SUCCESS" if not errors else "VALIDATION_FAILED"
    return EntityValidateResult(status, root, len(sample_dirs), len(errors), tuple(errors), 0 if not errors else 3)
