"""Primary CDF v2 entity-dataset publisher.

This module is the replacement for the old feature-manifest dataset path.  It writes
CAD-native graph inputs and separate part/face/edge/size labels.
"""

from __future__ import annotations

import json
import random
import shutil
from collections import Counter
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
from cad_dataset_factory.cdf.cadgen.flat_panel import FlatPanelFeatureSpec, FlatPanelSpec, build_flat_panel_part, export_step, write_flat_panel_outputs
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

DIVERSE_QUALITY_PROFILE = "sm_entity_v2_diverse_quality"
COMPACT_PROFILE = "sm_entity_v2_compact"
LEARNING_BALANCED_PROFILE = "sm_entity_v2_learning_balanced_v1"

LEARNING_FLAT_CASE_COUNTS = {
    "flat_plain": 4,
    "flat_hole_small": 5,
    "flat_hole_large": 5,
    "flat_multi_hole": 5,
    "flat_slot_short": 5,
    "flat_slot_long": 5,
    "flat_cutout_square": 5,
    "flat_cutout_rect": 5,
    "flat_combo_sparse": 5,
    "flat_combo_dense": 4,
}
LEARNING_BENT_CASE_COUNTS = {
    "single_flange": 12,
    "l_bracket": 12,
    "u_channel": 12,
    "hat_channel": 12,
}
LEARNING_OTHER_CASE_COUNTS = {
    "other_block": 8,
    "other_cylinder": 8,
}
LEARNING_BALANCED_BLOCK: tuple[str, ...] = tuple(
    case
    for group in (LEARNING_FLAT_CASE_COUNTS, LEARNING_BENT_CASE_COUNTS, LEARNING_OTHER_CASE_COUNTS)
    for case, count in group.items()
    for _ in range(count)
)
REQUIRED_SEGMENTATION_EDGE_CLASSES = (
    "OUTER_BOUNDARY",
    "HOLE_BOUNDARY",
    "SLOT_BOUNDARY",
    "CUTOUT_BOUNDARY",
    "BEND_EDGE",
    "FREE_EDGE",
    "INTERNAL",
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


def _write_split(path: Path, sample_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{sample_id}\n" for sample_id in sample_ids), encoding="utf-8")


def _write_default_splits(root: Path, records: list[dict[str, Any]]) -> None:
    sample_ids = [str(record["sample_id"]) for record in records]
    if len(sample_ids) > 1:
        train_ids = sample_ids[:-1]
        test_ids = sample_ids[-1:]
    else:
        train_ids = sample_ids
        test_ids = []
    _write_split(root / "splits" / "train.txt", train_ids)
    _write_split(root / "splits" / "test.txt", test_ids)


def _write_case_stratified_splits(root: Path, records: list[dict[str, Any]]) -> None:
    by_case: dict[str, list[str]] = {case: [] for case in PART_CASES}
    for record in records:
        by_case.setdefault(str(record["profile_case"]), []).append(str(record["sample_id"]))
    train_ids: list[str] = []
    test_ids: list[str] = []
    for case in PART_CASES:
        ids = by_case.get(case, [])
        if len(ids) < 4:
            raise CdfEntityPipelineError("insufficient_case_coverage", f"{DIVERSE_QUALITY_PROFILE} requires at least 4 samples per case")
        train_ids.extend(ids[:-1])
        test_ids.append(ids[-1])
    _write_split(root / "splits" / "train.txt", train_ids)
    _write_split(root / "splits" / "test.txt", test_ids)


def _sample_id_by_class(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_class: dict[str, list[str]] = {}
    for record in records:
        by_class.setdefault(str(record["part_class"]), []).append(str(record["sample_id"]))
    return by_class


def _sample_id_by_case(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_case: dict[str, list[str]] = {}
    for record in records:
        by_case.setdefault(str(record["profile_case"]), []).append(str(record["sample_id"]))
    return by_case


def _split_last_fraction(ids: list[str], *, minimum_test: int = 1) -> tuple[list[str], list[str]]:
    if len(ids) <= minimum_test:
        raise CdfEntityPipelineError("insufficient_split_support", "each split group needs at least one train and one test sample")
    test_count = max(minimum_test, int(round(len(ids) * 0.25)))
    test_count = min(test_count, len(ids) - 1)
    return ids[:-test_count], ids[-test_count:]


def _write_learning_balanced_splits(root: Path, records: list[dict[str, Any]]) -> None:
    part_train: list[str] = []
    part_test: list[str] = []
    for part_class, ids in sorted(_sample_id_by_class(records).items()):
        train_ids, test_ids = _split_last_fraction(ids)
        part_train.extend(train_ids)
        part_test.extend(test_ids)
        if not train_ids or not test_ids:
            raise CdfEntityPipelineError("insufficient_part_class_split", f"{part_class} must appear in part_train and part_test")

    segmentation_train: list[str] = []
    segmentation_test: list[str] = []
    for case, ids in sorted(_sample_id_by_case(records).items()):
        train_ids, test_ids = _split_last_fraction(ids)
        segmentation_train.extend(train_ids)
        segmentation_test.extend(test_ids)

    _write_split(root / "splits" / "part_train.txt", part_train)
    _write_split(root / "splits" / "part_test.txt", part_test)
    _write_split(root / "splits" / "segmentation_train.txt", segmentation_train)
    _write_split(root / "splits" / "segmentation_test.txt", segmentation_test)
    _write_split(root / "splits" / "train.txt", segmentation_train)
    _write_split(root / "splits" / "test.txt", segmentation_test)


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


def _case_plan_for_profile(profile: str, count: int) -> list[str]:
    if profile == LEARNING_BALANCED_PROFILE:
        if count < len(LEARNING_BALANCED_BLOCK) or count % len(LEARNING_BALANCED_BLOCK) != 0:
            raise CdfEntityPipelineError(
                "invalid_profile_count",
                f"{LEARNING_BALANCED_PROFILE} requires count >= {len(LEARNING_BALANCED_BLOCK)} and a multiple of {len(LEARNING_BALANCED_BLOCK)}",
            )
        repeats = count // len(LEARNING_BALANCED_BLOCK)
        return list(LEARNING_BALANCED_BLOCK) * repeats
    return [PART_CASES[index % len(PART_CASES)] for index in range(count)]


def _split_ids(root: Path, split_name: str) -> list[str]:
    path = root / "splits" / f"{split_name}.txt"
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _coverage_for_sample_ids(root: Path, sample_ids: list[str]) -> dict[str, Any]:
    part_counts: Counter[str] = Counter()
    face_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    case_counts: Counter[str] = Counter()
    index = _read_json(root / "dataset_index.json")
    record_by_id = {str(record["sample_id"]): record for record in index.get("samples", []) if isinstance(record, dict) and "sample_id" in record}
    for sample_id in sample_ids:
        sample_dir = root / "samples" / sample_id
        part_doc = _read_json(sample_dir / "metadata" / "part_class_label.json")
        face_doc = _read_json(sample_dir / "labels" / "face_segmentation.json")
        edge_doc = _read_json(sample_dir / "labels" / "edge_segmentation.json")
        part_counts[str(part_doc.get("part_class"))] += 1
        if sample_id in record_by_id:
            case_counts[str(record_by_id[sample_id].get("profile_case"))] += 1
        for item in face_doc.get("labels", []):
            if isinstance(item, dict):
                face_counts[str(item.get("semantic_label"))] += 1
        for item in edge_doc.get("labels", []):
            if isinstance(item, dict):
                edge_counts[str(item.get("semantic_label"))] += 1
    return {
        "sample_count": len(sample_ids),
        "part_class_counts": dict(sorted(part_counts.items())),
        "profile_case_counts": dict(sorted(case_counts.items())),
        "face_semantic_counts": dict(sorted(face_counts.items())),
        "edge_semantic_counts": dict(sorted(edge_counts.items())),
    }


def _write_label_coverage_report(root: Path, profile: str, records: list[dict[str, Any]]) -> None:
    all_ids = [str(record["sample_id"]) for record in records]
    split_names = sorted(path.stem for path in (root / "splits").glob("*.txt"))
    split_reports = {split_name: _coverage_for_sample_ids(root, _split_ids(root, split_name)) for split_name in split_names}
    report = {
        "schema": "CDF_ENTITY_LABEL_COVERAGE_REPORT_V1",
        "profile": profile,
        "sample_count": len(records),
        "overall": _coverage_for_sample_ids(root, all_ids),
        "splits": split_reports,
        "required_edge_semantics": list(REQUIRED_SEGMENTATION_EDGE_CLASSES),
    }
    if profile == LEARNING_BALANCED_PROFILE:
        required_part_classes = {"SM_FLAT_PANEL", "SM_SINGLE_FLANGE", "SM_L_BRACKET", "SM_U_CHANNEL", "SM_HAT_CHANNEL", "OTHER"}
        for split_name in ("part_train", "part_test"):
            observed = set(split_reports.get(split_name, {}).get("part_class_counts", {}))
            missing = sorted(required_part_classes - observed)
            if missing:
                raise CdfEntityPipelineError("part_split_coverage_failed", f"{split_name} missing part classes: {missing}")
        for split_name in ("segmentation_train", "segmentation_test"):
            observed = set(split_reports.get(split_name, {}).get("edge_semantic_counts", {}))
            missing = sorted(set(REQUIRED_SEGMENTATION_EDGE_CLASSES) - observed)
            if missing:
                raise CdfEntityPipelineError("segmentation_split_coverage_failed", f"{split_name} missing edge classes: {missing}")
    _write_json(root / "label_coverage_report.json", report)


def _flat_spec(sample_id: str, case: str, rng: random.Random) -> FlatPanelSpec:
    width = 128.0 + rng.randint(0, 6) * 8.0
    height = 86.0 + rng.randint(0, 6) * 6.0
    thickness = 1.0 + rng.randint(0, 3) * 0.25
    features: list[FlatPanelFeatureSpec] = []

    def add_hole(index: int, u: float, v: float, radius: float, role: FeatureRole = FeatureRole.UNKNOWN) -> None:
        features.append(
            FlatPanelFeatureSpec(
                feature_id=f"HOLE_{role.value}_{index:04d}",
                type=FeatureType.HOLE,
                role=role,
                center_uv_mm=(u, v),
                radius_mm=radius,
            )
        )

    def add_slot(index: int, u: float, v: float, slot_width: float, length: float, role: FeatureRole = FeatureRole.PASSAGE) -> None:
        features.append(
            FlatPanelFeatureSpec(
                feature_id=f"SLOT_{role.value}_{index:04d}",
                type=FeatureType.SLOT,
                role=role,
                center_uv_mm=(u, v),
                width_mm=slot_width,
                length_mm=length,
            )
        )

    def add_cutout(index: int, u: float, v: float, cutout_width: float, cutout_height: float, role: FeatureRole = FeatureRole.RELIEF) -> None:
        features.append(
            FlatPanelFeatureSpec(
                feature_id=f"CUTOUT_{role.value}_{index:04d}",
                type=FeatureType.CUTOUT,
                role=role,
                center_uv_mm=(u, v),
                width_mm=cutout_width,
                height_mm=cutout_height,
            )
        )

    if case in {"flat_hole", "flat_hole_small"}:
        add_hole(1, width * (0.32 + rng.uniform(-0.04, 0.04)), height * (0.50 + rng.uniform(-0.08, 0.08)), 2.6 + rng.random() * 1.2)
    elif case == "flat_hole_large":
        add_hole(1, width * (0.38 + rng.uniform(-0.04, 0.04)), height * (0.50 + rng.uniform(-0.08, 0.08)), 5.2 + rng.random() * 1.5, FeatureRole.MOUNT)
    elif case == "flat_multi_hole":
        add_hole(1, width * 0.30, height * 0.42, 3.0 + rng.random() * 0.8, FeatureRole.BOLT)
        add_hole(2, width * 0.70, height * 0.58, 4.0 + rng.random() * 1.0, FeatureRole.MOUNT)
    elif case in {"flat_slot", "flat_slot_short"}:
        add_slot(1, width * 0.58, height * (0.48 + rng.uniform(-0.06, 0.06)), 5.5 + rng.random() * 1.0, 17.0 + rng.random() * 4.0, FeatureRole.DRAIN)
    elif case == "flat_slot_long":
        add_slot(1, width * 0.58, height * (0.50 + rng.uniform(-0.05, 0.05)), 6.5 + rng.random() * 1.2, 30.0 + rng.random() * 8.0, FeatureRole.PASSAGE)
    elif case in {"flat_cutout", "flat_cutout_square"}:
        side = 13.0 + rng.random() * 4.0
        add_cutout(1, width * 0.55, height * 0.45, side, side, FeatureRole.RELIEF)
    elif case == "flat_cutout_rect":
        add_cutout(1, width * 0.55, height * 0.45, 22.0 + rng.random() * 5.0, 10.0 + rng.random() * 4.0, FeatureRole.RELIEF)
    elif case in {"flat_combo", "flat_combo_sparse"}:
        add_hole(1, width * 0.28, height * 0.58, 3.0 + rng.random(), FeatureRole.BOLT)
        add_slot(1, width * 0.70, height * 0.62, 5.5 + rng.random(), 20.0 + rng.random() * 4.0, FeatureRole.PASSAGE)
        add_cutout(1, width * 0.52, height * 0.26, 15.0 + rng.random() * 3.0, 9.0 + rng.random() * 3.0, FeatureRole.RELIEF)
    elif case == "flat_combo_dense":
        add_hole(1, width * 0.30, height * 0.62, 2.8 + rng.random() * 0.8, FeatureRole.BOLT)
        add_hole(2, width * 0.46, height * 0.56, 2.5 + rng.random() * 0.7, FeatureRole.UNKNOWN)
        add_slot(1, width * 0.70, height * 0.58, 5.0 + rng.random(), 18.0 + rng.random() * 4.0, FeatureRole.DRAIN)
        add_cutout(1, width * 0.50, height * 0.25, 12.0 + rng.random() * 3.0, 8.0 + rng.random() * 2.0, FeatureRole.RELIEF)
    elif case == "flat_plain":
        pass
    else:
        raise CdfEntityPipelineError("unsupported_flat_case", f"unsupported flat profile case: {case}")
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
    if case == "single_flange":
        web_width = 78.0 + rng.randint(0, 3) * 6.0
        flange_width = 18.0 + rng.randint(0, 3) * 3.0
    elif case == "l_bracket":
        web_width = 52.0 + rng.randint(0, 3) * 6.0
        flange_width = 40.0 + rng.randint(0, 3) * 4.0
    elif case == "u_channel":
        web_width = 58.0 + rng.randint(0, 4) * 7.0
        flange_width = 28.0 + rng.randint(0, 4) * 5.0
    else:
        web_width = 56.0 + rng.randint(0, 4) * 8.0
        flange_width = 26.0 + rng.randint(0, 4) * 5.0
    return BentPartSpec(
        sample_id=sample_id,
        part_name=f"{case.upper()}_{sample_id}",
        part_class=part_class,
        length_mm=120.0 + rng.randint(0, 4) * 10.0,
        web_width_mm=web_width,
        flange_width_mm=flange_width,
        side_wall_width_mm=28.0 + rng.randint(0, 3) * 4.0,
        thickness_mm=thickness,
        inner_radius_mm=max(0.75, thickness * 0.75),
        bend_angle_deg=90.0,
    )


def _write_other_outputs(sample_dir: Path, sample_id: str, case: str, rng: random.Random) -> None:
    try:
        import cadquery as cq
    except ModuleNotFoundError as exc:
        raise CdfEntityPipelineError("cadquery_unavailable", "CadQuery is required to generate OTHER examples", sample_id) from exc
    width = 36.0 + rng.randint(0, 4) * 6.0
    depth = 28.0 + rng.randint(0, 4) * 5.0
    height = 10.0 + rng.randint(0, 4) * 4.0
    if case == "other_cylinder":
        radius = min(width, depth) * 0.35
        shape = cq.Workplane("XY").circle(radius).extrude(height)
        params = {"radius_mm": radius, "height_mm": height}
    else:
        shape = cq.Workplane("XY").box(width, depth, height, centered=(False, False, True))
        params = {"width_mm": width, "depth_mm": depth, "height_mm": height}
    export_step(shape, sample_dir / "cad" / "input.step", f"{case.upper()}_{sample_id}")
    _write_json(
        sample_dir / "metadata" / "generator_params.json",
        {
            "schema": "CDF_GENERATOR_PARAMS_SM_V1",
            "sample_id": sample_id,
            "part_class": "OTHER",
            "canonical_part_name": f"{case.upper()}_{sample_id}",
            **params,
        },
    )


def _feature_contains_xy(feature: FlatPanelFeatureSpec, x: float, y: float, tolerance: float = 1.0) -> bool:
    u, v = feature.center_uv_mm
    if feature.type == FeatureType.HOLE:
        radius = float(feature.radius_mm or 0.0)
        return (x - u) ** 2 + (y - v) ** 2 <= (radius + tolerance) ** 2
    if feature.type == FeatureType.SLOT:
        length = float(feature.length_mm or 0.0)
        width = float(feature.width_mm or 0.0)
        return abs(x - u) <= length / 2.0 + tolerance and abs(y - v) <= width / 2.0 + tolerance
    if feature.type == FeatureType.CUTOUT:
        width = float(feature.width_mm or 0.0)
        height = float(feature.height_mm or 0.0)
        return abs(x - u) <= width / 2.0 + tolerance and abs(y - v) <= height / 2.0 + tolerance
    return False


def _matching_feature(feature_hints: tuple[FlatPanelFeatureSpec, ...], center_mm: list[float], *, tolerance: float = 1.0) -> FlatPanelFeatureSpec | None:
    if len(center_mm) < 2:
        return None
    x, y = float(center_mm[0]), float(center_mm[1])
    candidates = [feature for feature in feature_hints if _feature_contains_xy(feature, x, y, tolerance)]
    if not candidates:
        return None
    return min(candidates, key=lambda feature: (feature.type != FeatureType.HOLE, abs(float(feature.center_uv_mm[0]) - x) + abs(float(feature.center_uv_mm[1]) - y)))


def _label_for_face(graph: EntityBrepGraph, face_index: int, part_class: str, feature_hints: tuple[FlatPanelFeatureSpec, ...] = ()) -> FaceSemanticLabel:
    if part_class == "OTHER":
        return FaceSemanticLabel.OTHER
    face = graph.arrays["face_features"][face_index]
    area = float(face[0])
    max_area = float(np.max(graph.arrays["face_features"][:, 0])) if graph.arrays["face_features"].size else area
    normal_z = abs(float(face[9])) if face.shape[0] > 9 else 0.0
    if part_class == "SM_FLAT_PANEL":
        if area >= 0.5 * max_area and normal_z > 0.7:
            return FaceSemanticLabel.BASE_PANEL
        feature = _matching_feature(feature_hints, [float(face[4]), float(face[5]), float(face[6])], tolerance=1.5)
        if feature is not None:
            if feature.type == FeatureType.HOLE:
                return FaceSemanticLabel.HOLE_WALL
            if feature.type == FeatureType.SLOT:
                return FaceSemanticLabel.SLOT_WALL
            if feature.type == FeatureType.CUTOUT:
                return FaceSemanticLabel.CUTOUT_WALL
        return FaceSemanticLabel.SIDE_WALL
    if normal_z < 0.25:
        return FaceSemanticLabel.FLANGE
    if 0.25 <= normal_z <= 0.85:
        return FaceSemanticLabel.BEND
    return FaceSemanticLabel.BASE_PANEL


def _label_for_edge(
    graph: EntityBrepGraph,
    edge_index: int,
    part_class: str,
    case: str,
    adjacent_face_labels: tuple[FaceSemanticLabel, ...] = (),
    feature_hints: tuple[FlatPanelFeatureSpec, ...] = (),
) -> EdgeSemanticLabel:
    if part_class == "OTHER":
        return EdgeSemanticLabel.OTHER
    edge = graph.arrays["edge_features"][edge_index]
    curve_type = int(round(float(edge[0])))
    length = float(edge[1])
    bbox_x = abs(float(edge[2])) if edge.shape[0] > 2 else 0.0
    bbox_y = abs(float(edge[3])) if edge.shape[0] > 3 else 0.0
    bbox_z = abs(float(edge[4])) if edge.shape[0] > 4 else 0.0
    if bbox_x < 1.0e-6 and bbox_y < 1.0e-6 and bbox_z > 1.0e-6:
        return EdgeSemanticLabel.INTERNAL
    feature = _matching_feature(feature_hints, [float(edge[5]), float(edge[6]), float(edge[7])], tolerance=2.0)
    if curve_type in {2, 3}:
        if adjacent_face_labels and all(label in {FaceSemanticLabel.SIDE_WALL, FaceSemanticLabel.HOLE_WALL, FaceSemanticLabel.SLOT_WALL, FaceSemanticLabel.CUTOUT_WALL} for label in adjacent_face_labels):
            return EdgeSemanticLabel.INTERNAL
        if feature is not None and feature.type == FeatureType.SLOT:
            return EdgeSemanticLabel.SLOT_BOUNDARY
        return EdgeSemanticLabel.HOLE_BOUNDARY
    if feature is not None and feature.type == FeatureType.CUTOUT:
        return EdgeSemanticLabel.CUTOUT_BOUNDARY
    if feature is not None and feature.type == FeatureType.SLOT:
        return EdgeSemanticLabel.SLOT_BOUNDARY
    if part_class != "SM_FLAT_PANEL" and length > 20.0:
        return EdgeSemanticLabel.BEND_EDGE
    return EdgeSemanticLabel.OUTER_BOUNDARY if edge_index % 2 == 0 else EdgeSemanticLabel.FREE_EDGE


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _mesh_policy_for_graph(graph: EntityBrepGraph) -> GlobalMeshPolicy:
    part = graph.arrays["part_features"][0]
    bbox_x = abs(float(part[4])) if part.shape[0] > 4 else 0.0
    bbox_y = abs(float(part[5])) if part.shape[0] > 5 else 0.0
    planar = [value for value in (bbox_x, bbox_y) if value > 1.0e-6]
    far_field = _clamp((min(planar) / 20.0) if planar else 3.0, 3.0, 6.0)
    return GlobalMeshPolicy(h0_mm=far_field, h_min_mm=0.5, h_max_mm=8.0, growth_rate=1.25, quality_profile="AMG_QA_SHELL_V2")


def _target_size_for_edge(label: EdgeSemanticLabel, mesh: GlobalMeshPolicy, edge_fingerprint: dict[str, Any]) -> float:
    length = float(edge_fingerprint.get("length_mm", mesh.h0_mm))
    curve_type = int(edge_fingerprint.get("curve_type_id", 0))
    if label in {EdgeSemanticLabel.HOLE_BOUNDARY, EdgeSemanticLabel.SLOT_BOUNDARY, EdgeSemanticLabel.CUTOUT_BOUNDARY}:
        if label == EdgeSemanticLabel.HOLE_BOUNDARY and curve_type in {2, 3} and length > 0:
            return _clamp(length / 32.0, mesh.h_min_mm, 1.5)
        return _clamp(length / 24.0 if length > 0 else mesh.h0_mm * 0.35, 0.8, 1.5)
    if label == EdgeSemanticLabel.BEND_EDGE:
        thickness_like = abs(float(edge_fingerprint.get("bbox_mm", [0.0, 0.0, mesh.h_min_mm])[2])) if isinstance(edge_fingerprint.get("bbox_mm"), list) else mesh.h_min_mm
        return max(mesh.h_min_mm, min(mesh.h0_mm * 0.5, max(thickness_like, mesh.h_min_mm)))
    return mesh.h0_mm


def _is_size_control_edge(label: EdgeSemanticLabel) -> bool:
    return label in {
        EdgeSemanticLabel.OUTER_BOUNDARY,
        EdgeSemanticLabel.HOLE_BOUNDARY,
        EdgeSemanticLabel.SLOT_BOUNDARY,
        EdgeSemanticLabel.CUTOUT_BOUNDARY,
        EdgeSemanticLabel.BEND_EDGE,
        EdgeSemanticLabel.FREE_EDGE,
    }


def _write_entity_labels(
    sample_dir: Path,
    sample_id: str,
    graph: EntityBrepGraph,
    part_class: str,
    case: str,
    feature_hints: tuple[FlatPanelFeatureSpec, ...] = (),
) -> None:
    mesh = _mesh_policy_for_graph(graph)
    write_entity_label_json(
        sample_dir / "metadata" / "part_class_label.json",
        PartClassLabelDocument(sample_id=sample_id, part_class=part_class, source="cdf_entity_generator_v2"),
    )
    face_label_by_index = {int(record["index"]): _label_for_face(graph, int(record["index"]), part_class, feature_hints) for record in graph.entity_signatures["faces"]}
    face_labels = tuple(
        FaceSegmentationLabel(
            face_signature_id=record["signature_id"],
            semantic_label=face_label_by_index[int(record["index"])],
        )
        for record in graph.entity_signatures["faces"]
    )
    edge_items: list[EdgeSegmentationLabel] = []
    size_items: list[EdgeSizeRecord] = []
    for record in graph.entity_signatures["edges"]:
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        adjacent_face_labels = tuple(
            face_label_by_index[index]
            for index in fingerprint.get("adjacent_face_indices", [])
            if isinstance(index, int) and index in face_label_by_index
        )
        semantic = _label_for_edge(graph, int(record["index"]), part_class, case, adjacent_face_labels, feature_hints)
        edge_items.append(EdgeSegmentationLabel(edge_signature_id=record["signature_id"], semantic_label=semantic))
        if _is_size_control_edge(semantic):
            size_items.append(
                EdgeSizeRecord(
                    edge_signature_id=record["signature_id"],
                    target_size_mm=_target_size_for_edge(semantic, mesh, fingerprint),
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
    feature_hints: tuple[FlatPanelFeatureSpec, ...] = ()
    if case.startswith("flat"):
        spec = _flat_spec(sample_id, case, rng)
        generated = build_flat_panel_part(spec)
        write_flat_panel_outputs(sample_dir, generated)
        part_class = "SM_FLAT_PANEL"
        feature_hints = tuple(spec.features)
    elif case.startswith("other"):
        _write_other_outputs(sample_dir, sample_id, case, rng)
        part_class = "OTHER"
    else:
        generated = build_bent_part(_bent_spec(sample_id, case, rng))
        write_bent_part_outputs(sample_dir, generated)
        part_class = str(generated.spec.part_class.value)
    graph = extract_entity_brep_graph(sample_dir / "cad" / "input.step")
    write_entity_brep_graph(sample_dir / "graph" / "brep_graph.npz", graph)
    write_entity_graph_schema(sample_dir / "graph" / "graph_schema.json", graph)
    write_entity_signatures(sample_dir / "graph" / "entity_signatures.json", graph)
    _write_entity_labels(sample_dir, sample_id, graph, part_class, case, feature_hints)
    return {
        "sample_id": sample_id,
        "profile_case": case,
        "part_class": part_class,
        "path": f"samples/{sample_id}",
    }


def generate_entity_dataset(out_dir: str | Path, *, count: int, seed: int = 1, profile: str = "sm_entity_v2_compact") -> EntityGenerateResult:
    if count <= 0:
        raise CdfEntityPipelineError("invalid_count", "count must be positive")
    if profile not in {COMPACT_PROFILE, DIVERSE_QUALITY_PROFILE, LEARNING_BALANCED_PROFILE}:
        raise CdfEntityPipelineError("unsupported_profile", f"supported profiles: {COMPACT_PROFILE}, {DIVERSE_QUALITY_PROFILE}, {LEARNING_BALANCED_PROFILE}")
    if profile == DIVERSE_QUALITY_PROFILE and (count < 32 or count % len(PART_CASES) != 0):
        raise CdfEntityPipelineError("invalid_profile_count", f"{DIVERSE_QUALITY_PROFILE} requires count >= 32 and a multiple of {len(PART_CASES)}")
    case_plan = _case_plan_for_profile(profile, count)
    root = Path(out_dir)
    if root.exists():
        shutil.rmtree(root)
    (root / "samples").mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for index, case in enumerate(case_plan):
        sample_id = f"sample_{index + 1:06d}"
        records.append(_generate_one(root / "samples" / sample_id, sample_id, case, rng))
    dataset_index = {
        "schema": "CDF_ENTITY_DATASET_INDEX_SM_V2",
        "profile": profile,
        "seed": seed,
        "sample_count": len(records),
        "profile_case_counts": dict(sorted(Counter(str(record["profile_case"]) for record in records).items())),
        "samples": records,
        "splits": {
            "train": "splits/train.txt",
            "test": "splits/test.txt",
        },
    }
    _write_json(root / "dataset_index.json", dataset_index)
    if profile == DIVERSE_QUALITY_PROFILE:
        _write_case_stratified_splits(root, records)
    elif profile == LEARNING_BALANCED_PROFILE:
        _write_learning_balanced_splits(root, records)
        index = _read_json(root / "dataset_index.json")
        index["splits"].update(
            {
                "part_train": "splits/part_train.txt",
                "part_test": "splits/part_test.txt",
                "segmentation_train": "splits/segmentation_train.txt",
                "segmentation_test": "splits/segmentation_test.txt",
            }
        )
        _write_json(root / "dataset_index.json", index)
    else:
        _write_default_splits(root, records)
    _write_label_coverage_report(root, profile, records)
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
