"""Inference CLI for direct AMG v2 size-field prediction."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import torch

from ai_mesh_generator.amg.dataset import load_entity_dataset_sample
from ai_mesh_generator.amg.model.size_field import (
    BrepSizeFieldModel,
    SizeFieldModelError,
    build_size_field_document,
    build_size_field_graph_tensors,
    write_size_field_document,
)


class SizeFieldInferenceError(ValueError):
    """Raised when a size-field checkpoint or sample cannot be used."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def load_size_field_model(checkpoint_path: str | Path) -> BrepSizeFieldModel:
    path = Path(checkpoint_path)
    if not path.is_file():
        raise SizeFieldInferenceError("missing_checkpoint", f"checkpoint does not exist: {path}")
    checkpoint = torch.load(path, map_location="cpu")
    required = ("model_state_dict", "face_input_dim", "edge_input_dim", "hidden_dim")
    if not isinstance(checkpoint, dict) or any(key not in checkpoint for key in required):
        raise SizeFieldInferenceError("malformed_checkpoint", "checkpoint is missing size-field model metadata")
    model = BrepSizeFieldModel(int(checkpoint["face_input_dim"]), int(checkpoint["edge_input_dim"]), hidden_dim=int(checkpoint["hidden_dim"]))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def infer_size_field_document(
    *,
    sample_dir: str | Path,
    checkpoint_path: str | Path,
    h0_mm: float,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
    quality_profile: str = "AMG_QA_SHELL_V2",
) -> dict:
    sample = load_entity_dataset_sample(sample_dir)
    model = load_size_field_model(checkpoint_path)
    tensors = build_size_field_graph_tensors(sample, use_label_segmentation=False)
    if tensors.face_inputs.shape[1] != model.face_encoder[0].in_features or tensors.edge_inputs.shape[1] != model.edge_encoder[0].in_features:
        raise SizeFieldInferenceError("input_dimension_mismatch", "sample tensor dimensions do not match checkpoint")
    with torch.no_grad():
        output = model(tensors)
    return build_size_field_document(
        sample,
        output,
        h0_mm=h0_mm,
        h_min_mm=h_min_mm,
        h_max_mm=h_max_mm,
        growth_rate=growth_rate,
        quality_profile=quality_profile,
        include_face_sizes=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-infer-size-field")
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--h0-mm", type=float, default=3.0)
    parser.add_argument("--h-min-mm", type=float, default=0.5)
    parser.add_argument("--h-max-mm", type=float, default=8.0)
    parser.add_argument("--growth-rate", type=float, default=1.25)
    parser.add_argument("--quality-profile", default="AMG_QA_SHELL_V2")
    args = parser.parse_args(argv)
    try:
        document = infer_size_field_document(
            sample_dir=args.sample_dir,
            checkpoint_path=args.checkpoint,
            h0_mm=args.h0_mm,
            h_min_mm=args.h_min_mm,
            h_max_mm=args.h_max_mm,
            growth_rate=args.growth_rate,
            quality_profile=args.quality_profile,
        )
        write_size_field_document(args.out, document)
    except (SizeFieldInferenceError, SizeFieldModelError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "out": Path(args.out).as_posix()})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
