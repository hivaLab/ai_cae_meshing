from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_mesh_generator.validation.ansa_regression import (
    default_dataset_dir,
    default_model_path,
    run_ansa_regression,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ANSA production validation regression on deterministic test samples.")
    parser.add_argument("--sample-count", type=int, default=10, help="Number of deterministic test split samples to run.")
    parser.add_argument("--dataset-dir", type=Path, default=default_dataset_dir(ROOT), help="Dataset directory containing splits/test.txt.")
    parser.add_argument("--model-path", type=Path, default=default_model_path(ROOT), help="Exported AMG model artifact.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs" / "ansa_regression", help="Regression output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_ansa_regression(
        dataset_dir=args.dataset_dir,
        model_path=args.model_path,
        output_dir=args.output_dir,
        sample_count=args.sample_count,
        root=ROOT,
    )
    print(
        json.dumps(
            {
                "report": str((args.output_dir / "ANSA_REGRESSION_REPORT.json").resolve()),
                "markdown": str((ROOT / "ANSA_REGRESSION_REPORT.md").resolve()),
                "status": "ANSA_REGRESSION_ACCEPTED" if report["summary"]["accepted"] else "FAILED",
                "sample_count": report["summary"]["sample_count"],
                "passed_count": report["summary"]["passed_count"],
                "failed_count": report["summary"]["failed_count"],
            },
            indent=2,
        )
    )
    return 0 if report["summary"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
