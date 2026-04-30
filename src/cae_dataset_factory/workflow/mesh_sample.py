from __future__ import annotations

from pathlib import Path

from cae_dataset_factory.dataset.sample_writer import write_sample


def mesh_and_write_sample(assembly: dict, dataset_dir: Path | str, mesh_profile: dict) -> dict:
    return write_sample(assembly, dataset_dir, mesh_profile)
