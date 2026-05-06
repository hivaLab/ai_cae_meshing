"""CLI for the primary CDF v2 entity dataset pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from cad_dataset_factory.cdf.entity_pipeline import (
    CdfEntityPipelineError,
    generate_entity_dataset,
    validate_entity_dataset,
)
from cad_dataset_factory.cdf.oracle import run_ansa_probe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cdf-entity", description="CDF v2 B-rep entity dataset tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate clean CAD and v2 entity labels")
    generate.add_argument("--out", required=True, help="Output dataset directory")
    generate.add_argument("--count", type=int, required=True, help="Sample count")
    generate.add_argument("--seed", type=int, default=1, help="Deterministic seed")
    generate.add_argument("--profile", default="sm_entity_v2_compact", help="Entity generation profile")

    validate = subparsers.add_parser("validate", help="Validate a v2 entity dataset")
    validate.add_argument("--dataset", required=True, help="Dataset root")
    validate.add_argument("--require-quality", action="store_true", help="Require entity quality evaluations")

    probe = subparsers.add_parser("ansa-probe", help="Probe installed ANSA batch/Python runtime")
    probe.add_argument("--ansa-executable", required=True)
    probe.add_argument("--out", default="runs/ansa_probe/ansa_runtime_probe.json")
    probe.add_argument("--timeout-sec", type=int, default=90)

    evaluate = subparsers.add_parser("ansa-evaluate-size-field", help="Fail-closed real ANSA size-field evaluation gate")
    evaluate.add_argument("--sample-dir", required=True)
    evaluate.add_argument("--size-field", default="labels/mesh_size_field.json")
    evaluate.add_argument("--ansa-executable", required=True)
    evaluate.add_argument("--out", required=True)
    return parser


def _print(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_entity_dataset(args.out, count=args.count, seed=args.seed, profile=args.profile)
            _print(
                {
                    "status": result.status,
                    "dataset_root": result.dataset_root.as_posix(),
                    "requested_count": result.requested_count,
                    "generated_count": result.generated_count,
                    "blocked_count": result.blocked_count,
                    "reason": result.reason,
                }
            )
            return result.exit_code
        if args.command == "validate":
            result = validate_entity_dataset(args.dataset, require_quality=args.require_quality)
            _print(
                {
                    "status": result.status,
                    "dataset_root": result.dataset_root.as_posix(),
                    "sample_count": result.sample_count,
                    "error_count": result.error_count,
                    "errors": list(result.errors),
                }
            )
            return result.exit_code
        if args.command == "ansa-probe":
            result = run_ansa_probe(ansa_executable=args.ansa_executable, out=args.out, timeout_sec=args.timeout_sec)
            _print(
                {
                    "status": result.status,
                    "output_path": Path(result.output_path).as_posix(),
                    "returncode": result.returncode,
                    "error_code": result.error_code,
                }
            )
            return 0 if result.status == "OK" else 2
        if args.command == "ansa-evaluate-size-field":
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "status": "BLOCKED",
                "code": "ansa_size_field_binding_not_implemented",
                "sample_dir": Path(args.sample_dir).as_posix(),
                "size_field": args.size_field,
                "ansa_executable": args.ansa_executable,
                "message": "The v2 ANSA edge/face size-field binding is not complete; no mesh success is counted.",
            }
            out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _print(report)
            return 2
    except CdfEntityPipelineError as exc:
        _print({"status": "FAILED", "code": exc.code, "message": str(exc), "sample_id": exc.sample_id})
        return 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
