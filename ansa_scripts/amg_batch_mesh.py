from __future__ import annotations

from common_ansa_utils import run_ansa_batch_adapter


def run_batch_mesh(config_path: str) -> int:
    return run_ansa_batch_adapter(config_path, "amg_batch_mesh_adapter")
