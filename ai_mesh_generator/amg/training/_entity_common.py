"""Shared helpers for AMG v2 entity training CLIs."""

from __future__ import annotations

import json
from pathlib import Path

from ai_mesh_generator.amg.dataset import EntityDatasetSample, load_entity_dataset_sample


def write_json(path: str | Path, document: dict) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sample_paths_from_index(root: Path) -> dict[str, Path]:
    index_path = root / "dataset_index.json"
    if not index_path.is_file():
        return {path.name: path for path in sorted((root / "samples").glob("sample_*")) if path.is_dir()}
    index = json.loads(index_path.read_text(encoding="utf-8"))
    records = index.get("samples", [])
    return {
        str(record["sample_id"]): root / str(record["path"])
        for record in records
        if isinstance(record, dict) and "sample_id" in record and "path" in record
    }


def _split_sample_ids(root: Path, split: str) -> list[str]:
    split_path = root / "splits" / f"{split}.txt"
    if not split_path.is_file():
        raise ValueError(f"missing dataset split file: {split_path.as_posix()}")
    return [line.strip() for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_entity_sample_dirs(dataset_root: str | Path, *, split: str | None = None) -> list[Path]:
    root = Path(dataset_root)
    by_sample_id = _sample_paths_from_index(root)
    if split is None:
        paths = [by_sample_id[sample_id] for sample_id in sorted(by_sample_id)]
    else:
        paths = []
        for sample_id in _split_sample_ids(root, split):
            if sample_id not in by_sample_id:
                raise ValueError(f"split {split} references unknown sample id: {sample_id}")
            paths.append(by_sample_id[sample_id])
    return [path for path in paths if path.is_dir()]


def load_entity_samples(dataset_root: str | Path, *, split: str | None = None, require_quality: bool = False) -> list[EntityDatasetSample]:
    samples = [load_entity_dataset_sample(path, require_quality=require_quality) for path in iter_entity_sample_dirs(dataset_root, split=split)]
    if not samples:
        suffix = "" if split is None else f" for split {split}"
        raise ValueError(f"no entity samples found below {Path(dataset_root).as_posix()}{suffix}")
    return samples
