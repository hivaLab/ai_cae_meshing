"""CAD-native part classifier for AMG v2."""

from __future__ import annotations

import os
import pickle
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PART_CLASS_ORDER = (
    "SM_FLAT_PANEL",
    "SM_SINGLE_FLANGE",
    "SM_L_BRACKET",
    "SM_U_CHANNEL",
    "SM_HAT_CHANNEL",
    "OTHER",
)


class PartClassifierError(ValueError):
    """Raised when part-classifier training or inference fails."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PartClassifierTrainingResult:
    class_order: tuple[str, ...]
    sample_count: int
    feature_dim: int
    training_accuracy: float
    selected_model: str = "RandomForest"
    candidate_metrics: dict[str, dict[str, Any]] | None = None
    calibrated: bool = False
    feature_importances: tuple[float, ...] = ()


@dataclass
class PartClassifierEnsemble:
    selected_model: str
    model: Any
    classes_: np.ndarray
    calibrated: bool
    candidate_metrics: dict[str, dict[str, Any]]
    feature_importances_: np.ndarray

    def predict(self, features: np.ndarray) -> np.ndarray:
        return self.model.predict(features)

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(features)


@dataclass(frozen=True)
class PartClassPrediction:
    part_class: str
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool


def _load_sklearn() -> dict[str, Any]:
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
    except ModuleNotFoundError as exc:
        raise PartClassifierError("sklearn_unavailable", "scikit-learn is required for the part classifier") from exc
    return {
        "RandomForest": RandomForestClassifier,
        "ExtraTrees": ExtraTreesClassifier,
        "HistGradientBoosting": HistGradientBoostingClassifier,
        "CalibratedClassifierCV": CalibratedClassifierCV,
    }


def _graph_arrays(sample: Any) -> dict[str, np.ndarray] | None:
    if hasattr(sample, "graph"):
        return {key: np.asarray(value, dtype=np.float64) for key, value in sample.graph.arrays.items()}
    if isinstance(sample, dict):
        if "arrays" in sample and isinstance(sample["arrays"], dict):
            return {key: np.asarray(value, dtype=np.float64) for key, value in sample["arrays"].items()}
        if "part_features" in sample:
            return {"part_features": np.asarray(sample["part_features"], dtype=np.float64)}
    if hasattr(sample, "arrays"):
        return {key: np.asarray(value, dtype=np.float64) for key, value in sample.arrays.items()}
    return None


def _part_features(sample: Any) -> np.ndarray:
    arrays = _graph_arrays(sample)
    if arrays is None or "part_features" not in arrays:
        raise PartClassifierError("malformed_part_features", "sample does not expose part_features")
    rows = np.asarray(arrays["part_features"], dtype=np.float64)
    if rows.ndim != 2 or rows.shape[0] != 1:
        raise PartClassifierError("malformed_part_features", "part_features must have shape (1, P)")
    base = rows[0]
    if "face_features" not in arrays or "edge_features" not in arrays:
        return base

    face = np.asarray(arrays["face_features"], dtype=np.float64)
    edge = np.asarray(arrays["edge_features"], dtype=np.float64)
    if face.ndim != 2 or edge.ndim != 2:
        return base

    face_area = face[:, 0] if face.shape[1] > 0 and face.shape[0] else np.asarray([], dtype=np.float64)
    normal_z = np.abs(face[:, 9]) if face.shape[1] > 9 and face.shape[0] else np.asarray([], dtype=np.float64)
    face_wires = face[:, 11] if face.shape[1] > 11 and face.shape[0] else np.asarray([], dtype=np.float64)
    curve_type = edge[:, 0].round().astype(int) if edge.shape[1] > 0 and edge.shape[0] else np.asarray([], dtype=int)
    edge_length = edge[:, 1] if edge.shape[1] > 1 and edge.shape[0] else np.asarray([], dtype=np.float64)
    edge_bbox = edge[:, 2:5] if edge.shape[1] > 4 and edge.shape[0] else np.empty((0, 3), dtype=np.float64)

    total_area = float(face_area.sum()) if face_area.size else 0.0
    derived = np.asarray(
        [
            float(np.mean(face_area)) if face_area.size else 0.0,
            float(np.std(face_area)) if face_area.size else 0.0,
            float(np.max(face_area)) if face_area.size else 0.0,
            float(np.max(face_area) / max(total_area, 1.0e-9)) if face_area.size else 0.0,
            float(np.sum(normal_z > 0.85)),
            float(np.sum((normal_z >= 0.25) & (normal_z <= 0.85))),
            float(np.sum(normal_z < 0.25)),
            float(np.sum(face_wires > 1.0)),
            float(np.sum(curve_type == 1)),
            float(np.sum(curve_type == 2)),
            float(np.sum(curve_type == 3)),
            float(np.sum(curve_type >= 4)),
            float(np.mean(edge_length)) if edge_length.size else 0.0,
            float(np.std(edge_length)) if edge_length.size else 0.0,
            float(np.min(edge_length)) if edge_length.size else 0.0,
            float(np.max(edge_length)) if edge_length.size else 0.0,
            float(np.sum(np.all(edge_bbox[:, :2] < 1.0e-6, axis=1) & (edge_bbox[:, 2] > 1.0e-6))) if edge_bbox.size else 0.0,
            float(np.sum(edge_bbox[:, 2] < 1.0e-6)) if edge_bbox.size else 0.0,
        ],
        dtype=np.float64,
    )
    bbox = base[4:7] if base.shape[0] >= 7 else np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
    sorted_bbox = np.sort(np.abs(bbox))
    ratios = np.asarray(
        [
            float(sorted_bbox[0] / max(sorted_bbox[-1], 1.0e-9)) if sorted_bbox.shape[0] == 3 else 0.0,
            float(sorted_bbox[1] / max(sorted_bbox[-1], 1.0e-9)) if sorted_bbox.shape[0] == 3 else 0.0,
        ],
        dtype=np.float64,
    )
    return np.concatenate([base, derived, ratios])


def _part_label(sample: Any) -> str:
    if hasattr(sample, "labels"):
        value = sample.labels.part_class["part_class"]
    elif isinstance(sample, dict):
        value = sample["part_class"]
    else:
        raise PartClassifierError("missing_part_label", "sample does not expose a part_class label")
    if value not in PART_CLASS_ORDER:
        raise PartClassifierError("invalid_part_label", f"unsupported part class: {value}")
    return str(value)


def extract_part_feature_matrix(samples: Sequence[Any]) -> tuple[np.ndarray, list[str]]:
    if not samples:
        raise PartClassifierError("empty_dataset", "at least one sample is required")
    features = np.vstack([_part_features(sample) for sample in samples]).astype(np.float64)
    labels = [_part_label(sample) for sample in samples]
    return features, labels


def _class_counts(labels: Sequence[str]) -> dict[str, int]:
    return {label: int(sum(1 for item in labels if item == label)) for label in PART_CLASS_ORDER}


def _safe_feature_importances(model: Any, width: int) -> np.ndarray:
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return np.zeros((width,), dtype=np.float64)
    values = np.asarray(importances, dtype=np.float64)
    if values.shape != (width,):
        return np.zeros((width,), dtype=np.float64)
    return values


def _candidate_estimators(constructors: dict[str, Any], *, seed: int, n_estimators: int) -> dict[str, Any]:
    return {
        "RandomForest": constructors["RandomForest"](n_estimators=n_estimators, random_state=seed, class_weight="balanced", n_jobs=1),
        "ExtraTrees": constructors["ExtraTrees"](n_estimators=n_estimators, random_state=seed, class_weight="balanced", n_jobs=1),
        "HistGradientBoosting": constructors["HistGradientBoosting"](random_state=seed, learning_rate=0.06, max_iter=max(100, n_estimators // 2), l2_regularization=0.01),
    }


def _fit_calibrated_model(constructors: dict[str, Any], model: Any, features: np.ndarray, labels: list[str]) -> tuple[Any, bool]:
    counts = _class_counts(labels)
    active_counts = [count for count in counts.values() if count > 0]
    if not active_counts or min(active_counts) < 3:
        return model, False
    try:
        calibrated = constructors["CalibratedClassifierCV"](model, method="sigmoid", cv=3)
        calibrated.fit(features, labels)
        return calibrated, True
    except Exception:
        return model, False


def train_part_classifier(
    samples: Sequence[Any],
    *,
    seed: int = 1,
    n_estimators: int = 300,
    validation_samples: Sequence[Any] | None = None,
) -> tuple[Any, PartClassifierTrainingResult]:
    """Train a deterministic CAD-native ensemble and select the best tabular model."""

    constructors = _load_sklearn()
    features, labels = extract_part_feature_matrix(samples)
    if validation_samples:
        validation_features, validation_labels = extract_part_feature_matrix(validation_samples)
        selection_features = validation_features
        selection_labels = np.asarray(validation_labels)
        selection_source = "validation"
    else:
        selection_features = features
        selection_labels = np.asarray(labels)
        selection_source = "training"
    candidate_metrics: dict[str, dict[str, Any]] = {}
    fitted_models: dict[str, Any] = {}
    for name, estimator in _candidate_estimators(constructors, seed=seed, n_estimators=n_estimators).items():
        try:
            estimator.fit(features, labels)
            predictions = estimator.predict(selection_features)
            probabilities = estimator.predict_proba(selection_features)
            accuracy = float(np.mean(predictions == selection_labels))
            confidence = float(np.mean(np.max(probabilities, axis=1))) if probabilities.size else 0.0
            fitted_models[name] = estimator
            candidate_metrics[name] = {
                "status": "SUCCESS",
                "selection_source": selection_source,
                "accuracy": accuracy,
                "mean_confidence": confidence,
            }
        except Exception as exc:  # noqa: BLE001 - keep alternative models available.
            candidate_metrics[name] = {"status": "FAILED", "selection_source": selection_source, "error": str(exc), "accuracy": -1.0, "mean_confidence": 0.0}
    if not fitted_models:
        raise PartClassifierError("classifier_training_failed", "all candidate part classifiers failed to train")
    selected_name = sorted(
        fitted_models,
        key=lambda name: (float(candidate_metrics[name]["accuracy"]), float(candidate_metrics[name]["mean_confidence"]), name),
        reverse=True,
    )[0]
    selected_base = fitted_models[selected_name]
    importances = _safe_feature_importances(selected_base, features.shape[1])
    selected_model, calibrated = _fit_calibrated_model(constructors, selected_base, features, labels)
    wrapper = PartClassifierEnsemble(
        selected_model=selected_name,
        model=selected_model,
        classes_=np.asarray([str(value) for value in selected_model.classes_]),
        calibrated=calibrated,
        candidate_metrics=candidate_metrics,
        feature_importances_=importances,
    )
    predictions = wrapper.predict(features)
    result = PartClassifierTrainingResult(
        class_order=tuple(str(value) for value in wrapper.classes_),
        sample_count=int(features.shape[0]),
        feature_dim=int(features.shape[1]),
        training_accuracy=float(np.mean(predictions == np.asarray(labels))),
        selected_model=selected_name,
        candidate_metrics=candidate_metrics,
        calibrated=calibrated,
        feature_importances=tuple(float(value) for value in importances.tolist()),
    )
    return wrapper, result


def predict_part_class(model: Any, sample: Any, *, uncertainty_threshold: float = 0.60) -> PartClassPrediction:
    features = _part_features(sample).reshape(1, -1)
    probabilities = model.predict_proba(features)[0]
    classes = [str(value) for value in model.classes_]
    probability_map = {part_class: 0.0 for part_class in PART_CLASS_ORDER}
    probability_map.update({part_class: float(probability) for part_class, probability in zip(classes, probabilities, strict=True)})
    best_class = max(probability_map, key=probability_map.get)
    confidence = probability_map[best_class]
    return PartClassPrediction(
        part_class=best_class,
        confidence=confidence,
        probabilities=probability_map,
        uncertain=confidence < uncertainty_threshold,
    )


def save_part_classifier(path: str | Path, model: Any, metadata: PartClassifierTrainingResult) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        pickle.dump({"model": model, "metadata": metadata}, stream)


def load_part_classifier(path: str | Path) -> tuple[Any, PartClassifierTrainingResult]:
    with Path(path).open("rb") as stream:
        payload = pickle.load(stream)
    if not isinstance(payload, dict) or "model" not in payload or "metadata" not in payload:
        raise PartClassifierError("malformed_checkpoint", "part classifier checkpoint is malformed")
    return payload["model"], payload["metadata"]
