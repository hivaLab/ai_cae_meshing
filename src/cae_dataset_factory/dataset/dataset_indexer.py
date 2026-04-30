from __future__ import annotations

from pathlib import Path

import pandas as pd


INDEX_COLUMNS = [
    "sample_id",
    "sample_dir",
    "input_zip",
    "bdf_path",
    "graph_path",
    "label_path",
    "accepted",
    "oracle_base_size",
    "part_count",
    "connection_count",
    "defect_count",
]


def write_dataset_index(rows: list[dict], dataset_dir: Path | str) -> Path:
    dataset_dir = Path(dataset_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=INDEX_COLUMNS)
    path = dataset_dir / "dataset_index.parquet"
    frame.to_parquet(path, index=False)
    return path


def read_dataset_index(dataset_dir: Path | str) -> pd.DataFrame:
    return pd.read_parquet(Path(dataset_dir) / "dataset_index.parquet")
