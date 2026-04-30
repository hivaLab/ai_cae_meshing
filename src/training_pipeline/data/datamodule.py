from __future__ import annotations

from pathlib import Path

from .dataset import BRepAssemblyDataset


class MeshDataModule:
    def __init__(self, dataset_dir: Path | str) -> None:
        self.dataset_dir = Path(dataset_dir)

    def dataset(self, split: str = "train") -> BRepAssemblyDataset:
        return BRepAssemblyDataset(self.dataset_dir, split)
