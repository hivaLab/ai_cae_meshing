from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GenerationSpec:
    dataset_id: str
    seed: int
    accepted_target: int
    train_count: int
    val_count: int
    test_count: int
    product_family: str
    units: str
    backend: str
    min_parts_per_assembly: int
    defect_rate: float
    output_version: str


def load_generation_spec(path: Path | str) -> GenerationSpec:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return GenerationSpec(**payload)
