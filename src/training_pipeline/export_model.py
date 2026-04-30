from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def export_model(model: Path | str, output: Path | str) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(model, output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export-amg-model")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    print(export_model(args.model, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
