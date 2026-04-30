from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_mesh_generator.cad.importer import import_input_assembly
from ai_mesh_generator.graph.graph_builder import build_and_save_graph
from ai_mesh_generator.input.validator import validate_input_package_dir
from ai_mesh_generator.output.result_packager import validate_result_package
from ai_mesh_generator.workflow.run_mesh_job import run_mesh_job
from cae_mesh_common.bdf.bdf_validator import validate_bdf
from cae_mesh_common.io.package_reader import extract_job_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate-input")
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("build-graph")
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("run-mesh")
    p.add_argument("--job", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--backend", default="LOCAL_PROCEDURAL")
    p = sub.add_parser("validate-bdf")
    p.add_argument("--bdf", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("validate-result")
    p.add_argument("--result", required=True)
    p.add_argument("--output", required=False)
    args = parser.parse_args(argv)

    if args.command == "validate-input":
        job_dir = extract_job_package(args.job, Path(args.output).with_suffix(""))
        report = validate_input_package_dir(job_dir)
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return 0
    if args.command == "build-graph":
        job_dir = extract_job_package(args.job, Path(args.output) / "input")
        assembly = import_input_assembly(job_dir)
        build_and_save_graph(assembly, args.output)
        return 0
    if args.command == "run-mesh":
        result = run_mesh_job(args.job, args.model, args.output, args.backend)
        print(json.dumps(result["result_validation"], indent=2, sort_keys=True))
        return 0 if result["result_validation"]["passed"] else 1
    if args.command == "validate-bdf":
        result = validate_bdf(args.bdf)
        Path(args.output).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return 0 if result.passed else 1
    if args.command == "validate-result":
        result = validate_result_package(args.result)
        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
