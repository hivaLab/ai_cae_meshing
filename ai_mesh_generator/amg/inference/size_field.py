"""Inference CLI for direct AMG v2 size-field prediction."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch

from ai_mesh_generator.amg.dataset import load_entity_dataset_sample
from ai_mesh_generator.amg.model.part_classifier import PART_CLASS_ORDER, load_part_classifier, predict_part_class
from ai_mesh_generator.amg.model.segmentation import (
    EDGE_SEGMENTATION_CLASSES,
    FACE_SEGMENTATION_CLASSES,
    load_segmentation_model,
    predict_entity_segmentation_probabilities,
)
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


@dataclass(frozen=True)
class AiSizeFieldContext:
    part_probabilities: np.ndarray
    part_prediction: dict[str, Any]
    face_segmentation_probabilities: np.ndarray
    edge_segmentation_probabilities: np.ndarray


def _probability_histogram(probabilities: np.ndarray, classes: tuple[str, ...]) -> dict[str, int]:
    labels = probabilities.argmax(axis=1)
    return {label: int(np.sum(labels == index)) for index, label in enumerate(classes)}


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


def build_ai_size_field_context(
    *,
    sample: Any,
    part_classifier_path: str | Path,
    segmentation_checkpoint_path: str | Path,
) -> AiSizeFieldContext:
    part_model, _metadata = load_part_classifier(part_classifier_path)
    part_prediction = predict_part_class(part_model, sample, uncertainty_threshold=0.0)
    part_probabilities = np.asarray([part_prediction.probabilities[label] for label in PART_CLASS_ORDER], dtype=np.float32)
    segmentation_model = load_segmentation_model(segmentation_checkpoint_path)
    face_probs, edge_probs = predict_entity_segmentation_probabilities(sample, segmentation_model)
    return AiSizeFieldContext(
        part_probabilities=part_probabilities,
        part_prediction={
            "part_class": part_prediction.part_class,
            "confidence": part_prediction.confidence,
            "probabilities": part_prediction.probabilities,
            "uncertain": part_prediction.uncertain,
        },
        face_segmentation_probabilities=face_probs,
        edge_segmentation_probabilities=edge_probs,
    )


def infer_size_field_document(
    *,
    sample_dir: str | Path,
    checkpoint_path: str | Path,
    part_classifier_path: str | Path | None = None,
    segmentation_checkpoint_path: str | Path | None = None,
    h0_mm: float,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
    quality_profile: str = "AMG_QA_SHELL_V2",
) -> dict:
    sample = load_entity_dataset_sample(sample_dir)
    model = load_size_field_model(checkpoint_path)
    if part_classifier_path is None:
        raise SizeFieldInferenceError("missing_part_classifier", "part classifier checkpoint is required for AI size-field inference")
    if segmentation_checkpoint_path is None:
        raise SizeFieldInferenceError("missing_segmentation_checkpoint", "segmentation checkpoint is required for AI size-field inference")
    context = build_ai_size_field_context(
        sample=sample,
        part_classifier_path=part_classifier_path,
        segmentation_checkpoint_path=segmentation_checkpoint_path,
    )
    tensors = build_size_field_graph_tensors(
        sample,
        face_segmentation_probabilities=context.face_segmentation_probabilities,
        edge_segmentation_probabilities=context.edge_segmentation_probabilities,
        part_probabilities=context.part_probabilities,
    )
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
        edge_segmentation_probabilities=context.edge_segmentation_probabilities,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-infer-size-field")
    parser.add_argument("--sample-dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--part-classifier")
    parser.add_argument("--segmentation-checkpoint")
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
            part_classifier_path=args.part_classifier,
            segmentation_checkpoint_path=args.segmentation_checkpoint,
            h0_mm=args.h0_mm,
            h_min_mm=args.h_min_mm,
            h_max_mm=args.h_max_mm,
            growth_rate=args.growth_rate,
            quality_profile=args.quality_profile,
        )
        write_size_field_document(args.out, document)
        sample = load_entity_dataset_sample(args.sample_dir)
        context = build_ai_size_field_context(
            sample=sample,
            part_classifier_path=args.part_classifier,
            segmentation_checkpoint_path=args.segmentation_checkpoint,
        )
        context_path = Path(args.out).with_name("ai_size_field_context.json")
        context_path.write_text(
            json.dumps(
                {
                    "schema": "AMG_AI_SIZE_FIELD_CONTEXT_V1",
                    "part_prediction": context.part_prediction,
                    "face_segmentation_histogram": _probability_histogram(context.face_segmentation_probabilities, FACE_SEGMENTATION_CLASSES),
                    "edge_segmentation_histogram": _probability_histogram(context.edge_segmentation_probabilities, EDGE_SEGMENTATION_CLASSES),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except (SizeFieldInferenceError, SizeFieldModelError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "out": Path(args.out).as_posix()})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
