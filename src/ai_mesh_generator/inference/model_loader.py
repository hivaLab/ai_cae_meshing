from __future__ import annotations

import json
from pathlib import Path


def load_model(path: Path | str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"feature_order", "mean", "std", "weights"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"invalid model artifact, missing {sorted(missing)}")
    return payload
