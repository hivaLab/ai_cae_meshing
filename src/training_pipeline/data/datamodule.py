from __future__ import annotations

from pathlib import Path

from .dataset import load_training_arrays


class MeshDataModule:
    def __init__(self, dataset_dir: Path | str) -> None:
        self.dataset_dir = Path(dataset_dir)

    def arrays(self, split: str = "train"):
        return load_training_arrays(self.dataset_dir, split)
