"""CLI for optimizing an AMG v2 size field from the quality surrogate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ai_mesh_generator.amg.dataset import load_entity_dataset_sample
from ai_mesh_generator.amg.model.quality_surrogate import load_quality_surrogate, optimize_size_field, write_size_field
from ai_mesh_generator.amg.training._entity_common import write_json


def optimize_size_field_for_sample(
    sample_dir: str | Path,
    checkpoint: str | Path,
    output_path: str | Path,
    *,
    h0_mm: float,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
) -> dict:
    sample = load_entity_dataset_sample(sample_dir)
    model, _metadata = load_quality_surrogate(checkpoint)
    optimized = optimize_size_field(model, sample, h0_mm=h0_mm, h_min_mm=h_min_mm, h_max_mm=h_max_mm, growth_rate=growth_rate)
    write_size_field(output_path, optimized)
    report = {
        "schema": "AMG_SIZE_FIELD_OPTIMIZATION_REPORT_V1",
        "sample_id": sample.sample_id,
        "size_field_path": Path(output_path).as_posix(),
        "selected_entity_count": optimized.selected_entity_count,
        "growth_rate": growth_rate,
    }
    write_json(Path(output_path).with_suffix(".report.json"), report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg-optimize-size-field")
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--h0-mm", type=float, required=True)
    parser.add_argument("--h-min-mm", type=float, required=True)
    parser.add_argument("--h-max-mm", type=float, required=True)
    parser.add_argument("--growth-rate", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = optimize_size_field_for_sample(
            args.sample_dir,
            args.checkpoint,
            args.out,
            h0_mm=args.h0_mm,
            h_min_mm=args.h_min_mm,
            h_max_mm=args.h_max_mm,
            growth_rate=args.growth_rate,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "size_field_path": report["size_field_path"]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
