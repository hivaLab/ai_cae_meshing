"""Command line interface for the fail-closed CDF dataset pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from cad_dataset_factory.cdf.pipeline import CdfPipelineError, generate_dataset, validate_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cdf", description="CDF-SM-ANSA-V1 dataset tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a fail-closed CDF dataset")
    generate.add_argument("--config", default=None, help="Path to CDF config JSON")
    generate.add_argument("--out", required=True, help="Output dataset directory")
    generate.add_argument("--count", type=int, required=True, help="Accepted sample target count")
    generate.add_argument("--seed", type=int, default=None, help="Deterministic sampling seed")
    generate.add_argument("--require-ansa", action="store_true", help="Require real ANSA oracle reports for acceptance")

    validate = subparsers.add_parser("validate", help="Validate accepted CDF dataset samples")
    validate.add_argument("--dataset", required=True, help="Dataset root directory")
    validate.add_argument("--require-ansa", action="store_true", help="Require real ANSA oracle reports and mesh artifacts")
    return parser


def _print_result(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_dataset(
                config_path=args.config,
                out_dir=args.out,
                count=args.count,
                seed=args.seed,
                require_ansa=args.require_ansa,
            )
            _print_result(
                {
                    "status": result.status,
                    "dataset_root": Path(result.dataset_root).as_posix(),
                    "requested_count": result.requested_count,
                    "accepted_count": result.accepted_count,
                    "rejected_count": result.rejected_count,
                    "reason": result.reason,
                }
            )
            return result.exit_code
        if args.command == "validate":
            result = validate_dataset(dataset_root=args.dataset, require_ansa=args.require_ansa)
            _print_result(
                {
                    "status": result.status,
                    "dataset_root": Path(result.dataset_root).as_posix(),
                    "accepted_count": result.accepted_count,
                    "error_count": result.error_count,
                    "errors": list(result.errors),
                }
            )
            return result.exit_code
    except CdfPipelineError as exc:
        _print_result({"status": "FAILED", "code": exc.code, "message": str(exc)})
        return 1
    parser.error(f"unsupported command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
