from __future__ import annotations

from common_ansa_utils import load_config, write_result_manifest


def run_batch_mesh(config_path: str) -> int:
    config = load_config(config_path)
    write_result_manifest(config["output_dir"], True, {"mode": "amg_batch_mesh_adapter"})
    return 0
