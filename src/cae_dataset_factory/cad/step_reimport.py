from __future__ import annotations

from pathlib import Path


def reimport_step_metadata(path: Path | str) -> dict[str, object]:
    text = Path(path).read_text(encoding="utf-8")
    return {"path": str(path), "product_count": text.count("PRODUCT("), "valid_step": "ISO-10303-21" in text}
