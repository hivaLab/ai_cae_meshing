from __future__ import annotations

from pathlib import Path


def write_splits(sample_ids: list[str], dataset_dir: Path | str, train: int, val: int, test: int) -> dict[str, list[str]]:
    if train + val + test > len(sample_ids):
        raise ValueError("split counts exceed sample count")
    dataset_dir = Path(dataset_dir)
    split_dir = dataset_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    splits = {
        "train": sample_ids[:train],
        "val": sample_ids[train : train + val],
        "test": sample_ids[train + val : train + val + test],
    }
    for name, ids in splits.items():
        (split_dir / f"{name}.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
    return splits


def read_split(dataset_dir: Path | str, name: str) -> list[str]:
    path = Path(dataset_dir) / "splits" / f"{name}.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
