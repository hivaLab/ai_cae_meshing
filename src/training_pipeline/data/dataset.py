from __future__ import annotations

from pathlib import Path

import numpy as np

from cae_mesh_common.graph.hetero_graph import load_graph
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index
from cae_dataset_factory.dataset.split_builder import read_split


FEATURE_ORDER = ["part_count", "face_count", "connection_count", "defect_count", "mean_length", "mean_width", "mean_height"]


def load_training_arrays(dataset_dir: Path | str, split: str = "train") -> tuple[np.ndarray, np.ndarray, list[str]]:
    dataset_dir = Path(dataset_dir)
    index = read_dataset_index(dataset_dir)
    sample_ids = set(read_split(dataset_dir, split))
    rows = index[index["sample_id"].isin(sample_ids)] if sample_ids else index
    features = []
    targets = []
    ids = []
    for _, row in rows.iterrows():
        graph = load_graph(row["graph_path"])
        features.append([graph.graph_features[key] for key in FEATURE_ORDER])
        targets.append(float(row["oracle_base_size"]))
        ids.append(str(row["sample_id"]))
    return np.asarray(features, dtype=np.float64), np.asarray(targets, dtype=np.float64), ids
