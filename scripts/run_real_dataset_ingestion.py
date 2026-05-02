from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_mesh_generator.input.training_submission import validate_training_submission_dir


def run(dataset_dir: Path | str, output: Path | str | None = None) -> dict[str, object]:
    dataset_dir = Path(dataset_dir)
    result = validate_training_submission_dir(dataset_dir)
    report = {
        "dataset_dir": str(dataset_dir.resolve()),
        "valid_submission_structure": bool(result.get("valid", False)),
        "real_supervised_dataset_status": "REAL_SUPERVISED_DATASET_AVAILABLE"
        if result.get("valid", False)
        else "REAL_SUPERVISED_DATASET_NOT_AVAILABLE",
        "label_extraction_status": "not_performed_requires_ansa_mesh_pair_parser",
        "required_inputs": ["cad/raw.step", "ansa/final.ansa", "metadata/acceptance.csv", "metadata/quality_criteria.yaml"],
        "validation": result,
    }
    output_path = Path(output) if output else dataset_dir / "REAL_DATASET_INGESTION_REPORT.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = run(args.dataset_dir, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid_submission_structure"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
