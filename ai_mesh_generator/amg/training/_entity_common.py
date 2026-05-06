"""Shared helpers for AMG v2 entity training CLIs."""

from __future__ import annotations

import json
from pathlib import Path

from ai_mesh_generator.amg.dataset import EntityDatasetSample, load_entity_dataset_sample


def write_json(path: str | Path, document: dict) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_entity_sample_dirs(dataset_root: str | Path) -> list[Path]:
    root = Path(dataset_root)
    index_path = root / "dataset_index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        records = index.get("samples", [])
        paths = [root / str(record["path"]) for record in records if isinstance(record, dict) and "path" in record]
    else:
        paths = sorted(path for path in (root / "samples").glob("sample_*") if path.is_dir())
    return [path for path in paths if path.is_dir()]


def load_entity_samples(dataset_root: str | Path, *, require_quality: bool = False) -> list[EntityDatasetSample]:
    samples = [load_entity_dataset_sample(path, require_quality=require_quality) for path in iter_entity_sample_dirs(dataset_root)]
    if not samples:
        raise ValueError(f"no entity samples found below {Path(dataset_root).as_posix()}")
    return samples
