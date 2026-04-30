from __future__ import annotations

import json
from pathlib import Path


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_result_manifest(output_dir: str, success: bool, details: dict | None = None) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"success": success, "details": details or {}}
    path = output / "ansa_result_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path
