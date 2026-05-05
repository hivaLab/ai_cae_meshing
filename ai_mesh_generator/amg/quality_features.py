"""Shared graph/control features for AMG quality ranking and recommendation."""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np

from ai_mesh_generator.amg.dataset import AmgDatasetSample
from ai_mesh_generator.amg.model import ACTION_NAMES
from ai_mesh_generator.amg.model.graph_model import FEATURE_TYPES

QUALITY_CONTROL_SUMMARY_KEYS = (
    "edge_target_length_mm",
    "bend_target_length_mm",
    "flange_target_length_mm",
    "growth_rate",
    "radial_growth_rate",
    "perimeter_growth_rate",
    "washer_rings",
    "bend_rows",
    "circumferential_divisions",
    "end_arc_divisions",
    "straight_edge_divisions",
    "min_elements_across_width",
)


class AmgQualityFeatureError(ValueError):
    """Raised when quality-ranker feature construction cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def control_vector(manifest: Mapping[str, Any]) -> np.ndarray:
    """Return the manifest-control summary vector used by the quality ranker."""

    features = [feature for feature in manifest.get("features", []) if isinstance(feature, Mapping)]
    action_counts = {name: 0.0 for name in ACTION_NAMES}
    type_counts = {name: 0.0 for name in FEATURE_TYPES}
    scalars: dict[str, list[float]] = defaultdict(list)
    suppress_count = 0.0
    for feature in features:
        action = str(feature.get("action", ""))
        feature_type = str(feature.get("type", ""))
        if action in action_counts:
            action_counts[action] += 1.0
        if feature_type in type_counts:
            type_counts[feature_type] += 1.0
        if action == "SUPPRESS":
            suppress_count += 1.0
        controls = feature.get("controls", {})
        if isinstance(controls, Mapping):
            for key in QUALITY_CONTROL_SUMMARY_KEYS:
                value = controls.get(key)
                if isinstance(value, (int, float)):
                    scalars[key].append(float(value))
    denom = max(1.0, float(len(features)))
    vector = [action_counts[name] / denom for name in ACTION_NAMES]
    vector.extend(type_counts[name] / denom for name in FEATURE_TYPES)
    vector.append(suppress_count / denom)
    for key in QUALITY_CONTROL_SUMMARY_KEYS:
        values = scalars.get(key, [])
        vector.append(float(statistics.mean(values)) if values else 0.0)
        vector.append(float(len(values)) / denom)
    return np.asarray(vector, dtype=np.float32)


def graph_vector(sample: AmgDatasetSample) -> np.ndarray:
    """Return the graph summary vector used by the quality ranker."""

    arrays = sample.graph.arrays
    part = np.asarray(arrays["part_features"], dtype=np.float32)
    candidates = np.asarray(arrays["feature_candidate_features"], dtype=np.float32)
    if part.ndim != 2 or part.shape[0] != 1:
        raise AmgQualityFeatureError("malformed_part_features", "part_features must have shape (1, P)")
    if candidates.ndim != 2:
        raise AmgQualityFeatureError("malformed_candidate_features", "candidate feature matrix must be rank 2")
    candidate_mean = candidates.mean(axis=0) if candidates.shape[0] else np.zeros((14,), dtype=np.float32)
    candidate_std = candidates.std(axis=0) if candidates.shape[0] else np.zeros((14,), dtype=np.float32)
    return np.concatenate([part[0], candidate_mean, candidate_std]).astype(np.float32)


def build_quality_feature_vector(sample: AmgDatasetSample, manifest: Mapping[str, Any]) -> np.ndarray:
    """Return the exact graph/control vector used by training and recommendation."""

    return np.concatenate([graph_vector(sample), control_vector(manifest)]).astype(np.float32)
