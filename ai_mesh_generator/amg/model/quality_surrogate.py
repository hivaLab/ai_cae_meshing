"""Entity-local quality surrogate and constrained size-field optimizer."""

from __future__ import annotations

import json
import pickle
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


class QualitySurrogateError(ValueError):
    """Raised when the quality surrogate or optimizer cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class QualitySurrogateTrainingResult:
    row_count: int
    feature_dim: int
    hard_fail_rate: float
    mean_quality_margin: float


@dataclass(frozen=True)
class OptimizedSizeField:
    document: dict[str, Any]
    selected_entity_count: int
    projected_growth_rate: float


def _load_sklearn() -> tuple[Any, Any]:
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    except ModuleNotFoundError as exc:
        raise QualitySurrogateError("sklearn_unavailable", "scikit-learn is required for the quality surrogate") from exc
    return RandomForestClassifier, RandomForestRegressor


def _entity_feature(sample: Any, entity_type: str, signature_id: str) -> np.ndarray:
    graph = sample.graph
    collection = "edges" if entity_type == "EDGE" else "faces"
    array_name = "edge_features" if entity_type == "EDGE" else "face_features"
    index_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures[collection]}
    if signature_id not in index_by_sig:
        raise QualitySurrogateError("missing_entity_signature", f"unknown entity signature: {signature_id}")
    return np.asarray(graph.arrays[array_name][index_by_sig[signature_id]], dtype=np.float64)


def _row(sample: Any, record: dict[str, Any]) -> tuple[np.ndarray, float, int]:
    entity = _entity_feature(sample, record["entity_type"], record["entity_signature_id"])
    controls = np.asarray(
        [
            float(record["candidate_target_size_mm"]),
            float(record.get("candidate_neighbor_size_ratio_max") or record["candidate_growth_rate"]),
            float(record["candidate_growth_rate"]),
            1.0 if record["entity_type"] == "EDGE" else 0.0,
        ],
        dtype=np.float64,
    )
    quality_margin = float(record["measured_quality_margin"])
    hard_fail = int(bool(record["hard_fail"]))
    return np.concatenate([entity, controls]), quality_margin, hard_fail


def build_quality_surrogate_training_matrix(samples: Sequence[Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    margins: list[float] = []
    hard_fails: list[int] = []
    for sample in samples:
        for document in sample.labels.quality_evaluations:
            for record in document["entity_quality"]:
                if not record.get("metric_available", False):
                    continue
                row, margin, hard_fail = _row(sample, record)
                rows.append(row)
                margins.append(margin)
                hard_fails.append(hard_fail)
    if not rows:
        raise QualitySurrogateError("empty_quality_dataset", "no metric-available entity quality rows found")
    width = max(row.shape[0] for row in rows)
    padded = [
        np.pad(row, (0, width - row.shape[0]), mode="constant")
        if row.shape[0] < width
        else row
        for row in rows
    ]
    return np.vstack(padded), np.asarray(margins, dtype=np.float64), np.asarray(hard_fails, dtype=np.int64)


def train_quality_surrogate(samples: Sequence[Any], *, seed: int = 1) -> tuple[dict[str, Any], QualitySurrogateTrainingResult]:
    RandomForestClassifier, RandomForestRegressor = _load_sklearn()
    features, margins, hard_fails = build_quality_surrogate_training_matrix(samples)
    regressor = RandomForestRegressor(n_estimators=100, random_state=seed)
    regressor.fit(features, margins)
    if len(set(hard_fails.tolist())) >= 2:
        classifier = RandomForestClassifier(n_estimators=100, random_state=seed, class_weight="balanced")
        classifier.fit(features, hard_fails)
    else:
        classifier = None
    model = {"quality_margin_regressor": regressor, "hard_fail_classifier": classifier, "feature_dim": int(features.shape[1])}
    result = QualitySurrogateTrainingResult(
        row_count=int(features.shape[0]),
        feature_dim=int(features.shape[1]),
        hard_fail_rate=float(np.mean(hard_fails)),
        mean_quality_margin=float(np.mean(margins)),
    )
    return model, result


def _candidate_row(sample: Any, entity_type: str, signature_id: str, target_size: float, growth_rate: float) -> np.ndarray:
    entity = _entity_feature(sample, entity_type, signature_id)
    controls = np.asarray([target_size, growth_rate, growth_rate, 1.0 if entity_type == "EDGE" else 0.0], dtype=np.float64)
    return np.concatenate([entity, controls]).reshape(1, -1)


def predict_entity_quality(model: dict[str, Any], sample: Any, entity_type: str, signature_id: str, target_size: float, growth_rate: float) -> dict[str, float]:
    row = _candidate_row(sample, entity_type, signature_id, target_size, growth_rate)
    expected_dim = int(model["feature_dim"])
    if row.shape[1] < expected_dim:
        row = np.pad(row, ((0, 0), (0, expected_dim - row.shape[1])), mode="constant")
    if row.shape[1] != expected_dim:
        raise QualitySurrogateError("feature_dim_mismatch", "candidate row dimension does not match surrogate")
    margin = float(model["quality_margin_regressor"].predict(row)[0])
    classifier = model.get("hard_fail_classifier")
    if classifier is None:
        hard_fail_probability = 0.0
    else:
        classes = [int(value) for value in classifier.classes_]
        probabilities = classifier.predict_proba(row)[0]
        hard_fail_probability = float(probabilities[classes.index(1)]) if 1 in classes else 0.0
    return {"predicted_quality_margin": margin, "hard_fail_probability": hard_fail_probability}


def _edge_adjacency_from_vertices(sample: Any) -> list[tuple[int, int]]:
    edge_vertex = sample.graph.adjacency.get("EDGE_HAS_VERTEX")
    if edge_vertex is None or edge_vertex.size == 0:
        return []
    vertex_to_edges: dict[int, list[int]] = {}
    edge_offset = 1 + sample.graph.arrays["face_features"].shape[0]
    for edge_node, vertex_node in edge_vertex.tolist():
        edge_index = int(edge_node - edge_offset)
        if edge_index >= 0:
            vertex_to_edges.setdefault(int(vertex_node), []).append(edge_index)
    pairs: set[tuple[int, int]] = set()
    for edges in vertex_to_edges.values():
        for left in edges:
            for right in edges:
                if left < right:
                    pairs.add((left, right))
    return sorted(pairs)


def _project_edge_growth(sizes: list[float], pairs: list[tuple[int, int]], growth_rate: float, iterations: int = 8) -> list[float]:
    projected = [float(size) for size in sizes]
    for _ in range(iterations):
        changed = False
        for left, right in pairs:
            a = projected[left]
            b = projected[right]
            if a > b * growth_rate:
                projected[left] = b * growth_rate
                changed = True
            elif b > a * growth_rate:
                projected[right] = a * growth_rate
                changed = True
        if not changed:
            break
    return projected


def optimize_size_field(
    model: dict[str, Any],
    sample: Any,
    *,
    h0_mm: float,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
    quality_profile: str = "AMG_QA_SHELL_V2",
    cad_file: str = "cad/input.step",
    candidate_multipliers: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5),
) -> OptimizedSizeField:
    if not (0.0 < h_min_mm <= h0_mm <= h_max_mm):
        raise QualitySurrogateError("invalid_mesh_bounds", "expected 0 < h_min <= h0 <= h_max")
    if growth_rate < 1.0:
        raise QualitySurrogateError("invalid_growth_rate", "growth_rate must be >= 1")
    edge_records = sample.graph.entity_signatures["edges"]
    chosen_sizes: list[float] = []
    for record in edge_records:
        best_size = h0_mm
        best_score = float("inf")
        for multiplier in candidate_multipliers:
            size = min(max(h0_mm * multiplier, h_min_mm), h_max_mm)
            prediction = predict_entity_quality(model, sample, "EDGE", record["signature_id"], size, growth_rate)
            score = prediction["hard_fail_probability"] * 100.0 + max(0.0, prediction["predicted_quality_margin"])
            if score < best_score:
                best_score = score
                best_size = size
        chosen_sizes.append(best_size)
    projected = _project_edge_growth(chosen_sizes, _edge_adjacency_from_vertices(sample), growth_rate)
    document = {
        "schema_version": "AMG_SIZE_FIELD_SM_V2",
        "sample_id": sample.sample_id,
        "cad_file": cad_file,
        "unit": "mm",
        "global_mesh": {
            "h0_mm": h0_mm,
            "h_min_mm": h_min_mm,
            "h_max_mm": h_max_mm,
            "growth_rate": growth_rate,
            "quality_profile": quality_profile,
        },
        "edge_sizes": [
            {
                "edge_signature_id": record["signature_id"],
                "target_size_mm": float(min(max(size, h_min_mm), h_max_mm)),
                "source": "entity_quality_surrogate_optimizer",
            }
            for record, size in zip(edge_records, projected, strict=True)
        ],
        "face_sizes": [],
    }
    return OptimizedSizeField(document=document, selected_entity_count=len(edge_records), projected_growth_rate=growth_rate)


def save_quality_surrogate(path: str | Path, model: dict[str, Any], metadata: QualitySurrogateTrainingResult) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        pickle.dump({"model": model, "metadata": metadata}, stream)


def load_quality_surrogate(path: str | Path) -> tuple[dict[str, Any], QualitySurrogateTrainingResult]:
    with Path(path).open("rb") as stream:
        payload = pickle.load(stream)
    if not isinstance(payload, dict) or "model" not in payload or "metadata" not in payload:
        raise QualitySurrogateError("malformed_checkpoint", "quality surrogate checkpoint is malformed")
    return payload["model"], payload["metadata"]


def write_size_field(path: str | Path, size_field: OptimizedSizeField | dict[str, Any]) -> None:
    document = size_field.document if isinstance(size_field, OptimizedSizeField) else size_field
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
