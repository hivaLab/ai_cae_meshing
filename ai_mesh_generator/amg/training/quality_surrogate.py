"""Train the primary AMG v2 entity-local quality surrogate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ai_mesh_generator.amg.model.quality_surrogate import QualitySurrogateError, save_quality_surrogate, train_quality_surrogate
from ai_mesh_generator.amg.training._entity_common import load_entity_samples, write_json


def train_quality_surrogate_from_dataset(dataset_root: str | Path, output_dir: str | Path, *, seed: int = 1) -> dict:
    samples = load_entity_samples(dataset_root, require_quality=True)
    model, metadata = train_quality_surrogate(samples, seed=seed)
    out = Path(output_dir)
    save_quality_surrogate(out / "model.pkl", model, metadata)
    metrics = {
        "schema": "AMG_QUALITY_SURROGATE_METRICS_V1",
        "dataset_root": Path(dataset_root).as_posix(),
        "sample_count": len(samples),
        "row_count": metadata.row_count,
        "feature_dim": metadata.feature_dim,
        "hard_fail_rate": metadata.hard_fail_rate,
        "mean_quality_margin": metadata.mean_quality_margin,
        "model_path": (out / "model.pkl").as_posix(),
    }
    write_json(out / "metrics.json", metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg-train-quality-surrogate")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metrics = train_quality_surrogate_from_dataset(args.dataset, args.out, seed=args.seed)
    except (QualitySurrogateError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "metrics_path": str(Path(args.out) / "metrics.json"), "row_count": metrics["row_count"]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
