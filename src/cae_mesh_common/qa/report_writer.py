from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_qa_json(metrics: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_qa_html(metrics: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in sorted(metrics.items()))
    html = f"<html><head><title>QA Report</title></head><body><h1>QA Report</h1><table>{rows}</table></body></html>"
    path.write_text(html, encoding="utf-8")
    return path
