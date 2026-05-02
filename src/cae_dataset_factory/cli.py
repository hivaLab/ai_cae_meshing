from __future__ import annotations

import argparse
import json
from pathlib import Path

from cae_dataset_factory.config.generation_spec import load_generation_spec
from cae_dataset_factory.dataset.dataset_validator import validate_dataset
from cae_dataset_factory.dataset.split_builder import write_splits
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph
from cae_dataset_factory.graph.pyg_exporter import export_graph
from cae_dataset_factory.workflow.build_dataset import build_dataset
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cdf")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate-spec")
    p.add_argument("--spec", required=True)
    p = sub.add_parser("generate")
    p.add_argument("--spec", required=True)
    p.add_argument("--num-samples", type=int, default=None)
    p.add_argument("--output", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("validate-dataset")
    p.add_argument("--dataset", required=True)
    p = sub.add_parser("build-graphs")
    p.add_argument("--dataset", required=True)
    p = sub.add_parser("build-split")
    p.add_argument("--dataset", required=True)
    p.add_argument("--train", type=float, default=0.8)
    p.add_argument("--val", type=float, default=0.1)
    p.add_argument("--test", type=float, default=0.1)
    p = sub.add_parser("mesh")
    p.add_argument("--dataset", required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--backend", default="SYNTHETIC_ORACLE")
    p = sub.add_parser("evaluate")
    p.add_argument("--dataset", required=True)
    args = parser.parse_args(argv)

    if args.command == "validate-spec":
        spec = load_generation_spec(args.spec)
        print(json.dumps(spec.__dict__, indent=2, sort_keys=True))
        return 0
    if args.command == "generate":
        result = build_dataset(args.spec, args.output, args.num_samples, force=args.force)
        print(json.dumps(result["manifest"], indent=2, sort_keys=True))
        return 0
    if args.command == "validate-dataset":
        summary = validate_dataset(args.dataset)
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0 if summary.passed else 1
    if args.command == "build-graphs":
        for sample_dir in sorted((Path(args.dataset) / "samples").iterdir()):
            assembly_path = sample_dir / "assembly.json"
            if assembly_path.exists():
                assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
                export_graph(build_brep_graph(assembly), sample_dir / "graphs" / "graph.pt")
        return 0
    if args.command == "build-split":
        index = read_dataset_index(args.dataset)
        sample_ids = list(index["sample_id"])
        total = len(sample_ids)
        train = int(total * args.train)
        val = int(total * args.val)
        test = total - train - val
        write_splits(sample_ids, args.dataset, train, val, test)
        return 0
    if args.command in {"mesh", "evaluate"}:
        summary = validate_dataset(args.dataset)
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0 if summary.passed else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
