from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml


ACCEPTANCE_COLUMNS = {
    "sample_id",
    "acceptance_status",
    "reviewer",
    "review_date",
    "use_for_training",
    "reject_reason",
    "notes",
}
ACCEPTANCE_STATUSES = {"accepted", "rejected", "needs_manual_review", "unknown"}


def validate_training_submission_dir(root: Path | str) -> dict[str, Any]:
    """Validate a real CAD/Mesh pair submission for supervised dataset building."""

    root = Path(root)
    required = {
        "cad/raw.step": root / "cad" / "raw.step",
        "ansa/final.ansa": root / "ansa" / "final.ansa",
        "metadata/acceptance.csv": root / "metadata" / "acceptance.csv",
        "metadata/quality_criteria.yaml": root / "metadata" / "quality_criteria.yaml",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing required training submission artifacts: {missing}")

    acceptance_rows = _read_acceptance(required["metadata/acceptance.csv"])
    quality_criteria = _read_quality_criteria(required["metadata/quality_criteria.yaml"])
    optional = {
        "solver/final.bdf": (root / "solver" / "final.bdf").exists(),
        "reports/ansa_quality_report": any((root / "reports").glob("ansa_quality_report.*"))
        if (root / "reports").exists()
        else False,
    }
    return {
        "root": str(root.resolve()),
        "valid": True,
        "required": {name: str(path.resolve()) for name, path in required.items()},
        "optional_present": optional,
        "acceptance_rows": acceptance_rows,
        "quality_criteria": quality_criteria,
        "material_constants_required": False,
        "notes": [
            "E, density, and Poisson ratio are not required for mesh automation submissions.",
            "BDF and ANSA quality report are optional inputs because they can be exported by the pipeline when ANSA is available.",
        ],
    }


def _read_acceptance(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(ACCEPTANCE_COLUMNS - columns)
        if missing:
            raise ValueError(f"acceptance.csv is missing columns: {missing}")
        rows = []
        for row in reader:
            status = str(row.get("acceptance_status", "")).strip().lower()
            if status not in ACCEPTANCE_STATUSES:
                raise ValueError(f"invalid acceptance_status {status!r}; expected one of {sorted(ACCEPTANCE_STATUSES)}")
            rows.append({key: str(row.get(key, "")).strip() for key in ACCEPTANCE_COLUMNS})
    if not rows:
        raise ValueError("acceptance.csv must contain at least one row")
    return rows


def _read_quality_criteria(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("quality_criteria.yaml must contain a mapping")
    shell = data.get("shell")
    if not isinstance(shell, dict):
        raise ValueError("quality_criteria.yaml must define a shell criteria mapping")
    required_shell_keys = {"max_aspect_ratio", "max_skew_deg", "min_jacobian"}
    missing = sorted(required_shell_keys - set(shell))
    if missing:
        raise ValueError(f"quality_criteria.yaml shell section is missing keys: {missing}")
    return data
