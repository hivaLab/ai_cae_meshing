"""Command line interface for the fail-closed CDF dataset pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from cad_dataset_factory.cdf.pipeline import CdfPipelineError, generate_dataset, validate_dataset
from cad_dataset_factory.cdf.oracle import run_ansa_probe
from cad_dataset_factory.cdf.quality import CdfQualityExplorationError, run_quality_exploration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cdf", description="CDF-SM-ANSA-V1 dataset tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a fail-closed CDF dataset")
    generate.add_argument("--config", default=None, help="Path to CDF config JSON")
    generate.add_argument("--out", required=True, help="Output dataset directory")
    generate.add_argument("--count", type=int, required=True, help="Accepted sample target count")
    generate.add_argument("--seed", type=int, default=None, help="Deterministic sampling seed")
    generate.add_argument("--require-ansa", action="store_true", help="Require real ANSA oracle reports for acceptance")
    generate.add_argument("--ansa-executable", default=None, help="Explicit ANSA executable/batch file path")
    generate.add_argument("--profile", default="flat_hole_pilot_v1", help="Generation profile, e.g. sm_mixed_benchmark_v1")

    validate = subparsers.add_parser("validate", help="Validate accepted CDF dataset samples")
    validate.add_argument("--dataset", required=True, help="Dataset root directory")
    validate.add_argument("--require-ansa", action="store_true", help="Require real ANSA oracle reports and mesh artifacts")

    probe = subparsers.add_parser("ansa-probe", help="Probe installed ANSA batch/Python runtime")
    probe.add_argument("--ansa-executable", required=True, help="Explicit ANSA executable/batch file path")
    probe.add_argument("--out", default="runs/ansa_probe/ansa_runtime_probe.json", help="Probe report JSON path")
    probe.add_argument("--timeout-sec", type=int, default=90, help="Probe timeout in seconds")

    quality = subparsers.add_parser("quality-explore", help="Run real ANSA perturbation-based quality exploration")
    quality.add_argument("--dataset", required=True, help="Accepted CDF dataset root")
    quality.add_argument("--out", required=True, help="Quality exploration output directory")
    quality.add_argument("--perturbations-per-sample", type=int, default=3)
    quality.add_argument("--limit", type=int, default=None, help="Optional accepted sample limit for fast iteration")
    quality.add_argument("--ansa-executable", required=True, help="Explicit ANSA executable/batch file path")
    quality.add_argument("--timeout-sec", type=int, default=180)
    return parser


def _print_result(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            env = dict(os.environ)
            if args.ansa_executable:
                env["ANSA_EXECUTABLE"] = str(args.ansa_executable)
            result = generate_dataset(
                config_path=args.config,
                out_dir=args.out,
                count=args.count,
                seed=args.seed,
                require_ansa=args.require_ansa,
                env=env,
                profile=args.profile,
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
        if args.command == "ansa-probe":
            result = run_ansa_probe(ansa_executable=args.ansa_executable, out=args.out, timeout_sec=args.timeout_sec)
            _print_result(
                {
                    "status": result.status,
                    "output_path": Path(result.output_path).as_posix(),
                    "returncode": result.returncode,
                    "error_code": result.error_code,
                }
            )
            return 0 if result.status == "OK" else 2
        if args.command == "quality-explore":
            result = run_quality_exploration(
                dataset_root=args.dataset,
                output_dir=args.out,
                perturbations_per_sample=args.perturbations_per_sample,
                limit=args.limit,
                ansa_executable=args.ansa_executable,
                timeout_sec_per_sample=args.timeout_sec,
            )
            _print_result(
                {
                    "status": result.status,
                    "output_dir": result.output_dir,
                    "summary_path": result.summary_path,
                    "baseline_count": result.baseline_count,
                    "evaluated_count": result.evaluated_count,
                    "passed_count": result.passed_count,
                    "failed_count": result.failed_count,
                    "blocked_count": result.blocked_count,
                    "quality_score_variance": result.quality_score_variance,
                }
            )
            return 0 if result.status == "SUCCESS" else 2
    except CdfPipelineError as exc:
        _print_result({"status": "FAILED", "code": exc.code, "message": str(exc)})
        return 1
    except CdfQualityExplorationError as exc:
        _print_result({"status": "BLOCKED", "code": exc.code, "message": str(exc)})
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
