from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_mesh_generator.validation.step_ingestion_regression import run_step_ingestion_regression


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_step_ingestion_regression")
    parser.add_argument("--sample-count", type=int, default=5)
    parser.add_argument("--cad-dir", default=None)
    parser.add_argument("--output-dir", default=str(ROOT / "runs" / "step_ingestion_regression"))
    args = parser.parse_args(argv)
    report = run_step_ingestion_regression(args.output_dir, sample_count=args.sample_count, cad_dir=args.cad_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
