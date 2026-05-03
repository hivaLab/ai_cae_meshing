"""Real manifest-supervised AMG training on accepted CDF datasets."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from ai_mesh_generator.amg.dataset import AmgDatasetSample, iter_amg_dataset_samples, load_dataset_index
from ai_mesh_generator.amg.model import ACTION_NAMES, AmgGraphModel, AmgModelOutput, GraphBatch, ModelDimensions, apply_action_mask, build_graph_batch
from ai_mesh_generator.amg.model.graph_model import FEATURE_TYPES, PART_CLASSES


class AmgRealTrainingError(ValueError):
    """Raised when real AMG dataset training cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class RealTrainingConfig:
    dataset_root: Path
    output_dir: Path
    epochs: int = 5
    batch_size: int = 16
    seed: int = 1
    learning_rate: float = 1.0e-3
    hidden_dim: int = 32


@dataclass(frozen=True)
class ManifestSupervisionTargets:
    part_class_targets: torch.Tensor
    feature_type_targets: torch.Tensor
    feature_action_targets: torch.Tensor
    log_h_targets: torch.Tensor
    log_h_mask: torch.Tensor
    division_targets: torch.Tensor
    division_mask: torch.Tensor
    quality_risk_targets: torch.Tensor
    matched_feature_count: int
    manifest_feature_count: int
    candidate_count: int


@dataclass(frozen=True)
class RealLossBreakdown:
    total: torch.Tensor
    part_class: torch.Tensor
    feature_type: torch.Tensor
    feature_action: torch.Tensor
    log_h: torch.Tensor
    division: torch.Tensor
    quality_risk: torch.Tensor

    def as_metrics(self, prefix: str) -> dict[str, float]:
        return {
            f"{prefix}_loss_total": float(self.total.detach().cpu()),
            f"{prefix}_loss_part_class": float(self.part_class.detach().cpu()),
            f"{prefix}_loss_feature_type": float(self.feature_type.detach().cpu()),
            f"{prefix}_loss_feature_action": float(self.feature_action.detach().cpu()),
            f"{prefix}_loss_log_h": float(self.log_h.detach().cpu()),
            f"{prefix}_loss_division": float(self.division.detach().cpu()),
            f"{prefix}_loss_quality_risk": float(self.quality_risk.detach().cpu()),
        }


@dataclass(frozen=True)
class RealTrainingResult:
    checkpoint_path: str
    metrics_path: str
    training_config_path: str
    metrics: dict[str, Any]


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgRealTrainingError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgRealTrainingError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgRealTrainingError("json_document_not_object", f"{path} must contain a JSON object", path)
    return loaded


def _require_real_sample(sample_dir: Path) -> None:
    acceptance = _read_json(sample_dir / "reports" / "sample_acceptance.json", "missing_sample_acceptance")
    execution = _read_json(sample_dir / "reports" / "ansa_execution_report.json", "missing_execution_report")
    quality = _read_json(sample_dir / "reports" / "ansa_quality_report.json", "missing_quality_report")
    mesh_path = sample_dir / "meshes" / "ansa_oracle_mesh.bdf"

    accepted_by = acceptance.get("accepted_by")
    if acceptance.get("accepted") is not True or not isinstance(accepted_by, Mapping) or accepted_by.get("ansa_oracle") is not True:
        raise AmgRealTrainingError("dataset_not_real_accepted", "sample acceptance must be real ANSA accepted", sample_dir)
    if execution.get("accepted") is not True:
        raise AmgRealTrainingError("dataset_not_real_accepted", "ANSA execution report must be accepted", sample_dir)
    if quality.get("accepted") is not True:
        raise AmgRealTrainingError("dataset_not_real_accepted", "ANSA quality report must be accepted", sample_dir)
    if execution.get("ansa_version") in {"unavailable", "mock-ansa"}:
        raise AmgRealTrainingError("dataset_not_real_accepted", "ANSA version must be real", sample_dir)
    outputs = execution.get("outputs", {})
    if isinstance(outputs, Mapping) and "controlled_failure_reason" in outputs:
        raise AmgRealTrainingError("dataset_not_real_accepted", "controlled failure report cannot supervise training", sample_dir)
    quality_payload = quality.get("quality", {})
    if not isinstance(quality_payload, Mapping) or int(quality_payload.get("num_hard_failed_elements", 1)) != 0:
        raise AmgRealTrainingError("dataset_not_real_accepted", "accepted training samples require zero hard failed elements", sample_dir)
    if not mesh_path.is_file() or mesh_path.stat().st_size <= 0:
        raise AmgRealTrainingError("dataset_not_real_accepted", "accepted training samples require a non-empty oracle BDF", mesh_path)
    head = mesh_path.read_text(encoding="utf-8", errors="ignore")[:256].lower()
    if "mock" in head or "placeholder" in head:
        raise AmgRealTrainingError("dataset_not_real_accepted", "placeholder or mock meshes cannot supervise training", mesh_path)


def validate_real_training_dataset(dataset_root: str | Path) -> list[AmgDatasetSample]:
    """Load only samples that satisfy the real ANSA accepted dataset gate."""

    root = Path(dataset_root)
    index = load_dataset_index(root)
    if not index.get("accepted_samples"):
        raise AmgRealTrainingError("empty_real_dataset", "dataset has no accepted samples", root)
    samples = list(iter_amg_dataset_samples(root))
    if not samples:
        raise AmgRealTrainingError("empty_real_dataset", "dataset has no loadable accepted samples", root)
    for sample in samples:
        _require_real_sample(sample.sample_dir)
        if sample.manifest.status != "VALID":
            raise AmgRealTrainingError("dataset_not_real_accepted", "training labels require VALID AMG manifests", sample.manifest.manifest_path)
    return samples


def _decode_metadata_array(sample: AmgDatasetSample) -> list[dict[str, Any]]:
    arrays = sample.graph.arrays
    candidate_count = int(arrays["feature_candidate_features"].shape[0])
    raw = arrays.get("feature_candidate_metadata_json")
    if raw is None:
        return [{} for _ in range(candidate_count)]
    metadata: list[dict[str, Any]] = []
    for item in raw:
        try:
            loaded = json.loads(str(item))
        except json.JSONDecodeError as exc:
            raise AmgRealTrainingError("malformed_candidate_metadata", "candidate metadata JSON must parse", sample.graph.graph_npz_path) from exc
        if not isinstance(loaded, dict):
            raise AmgRealTrainingError("malformed_candidate_metadata", "candidate metadata entries must be objects", sample.graph.graph_npz_path)
        metadata.append(loaded)
    if len(metadata) != candidate_count:
        raise AmgRealTrainingError("malformed_candidate_metadata", "candidate metadata count must match candidate rows", sample.graph.graph_npz_path)
    return metadata


def _signature_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        if "geometry_signature" in value:
            return str(value["geometry_signature"])
        return json.dumps(dict(value), sort_keys=True)
    if value is None:
        return None
    return str(value)


def _match_manifest_features(sample: AmgDatasetSample) -> list[dict[str, Any]]:
    metadata = _decode_metadata_array(sample)
    manifest_features = [dict(feature) for feature in sample.manifest.manifest.get("features", []) if isinstance(feature, Mapping)]
    if len(metadata) == 0:
        raise AmgRealTrainingError("empty_candidate_batch", "real training requires feature candidates", sample.sample_dir)
    if len(manifest_features) == 0:
        raise AmgRealTrainingError("empty_manifest_features", "real training requires manifest feature labels", sample.manifest.manifest_path)

    unmatched = list(range(len(manifest_features)))
    matches: list[dict[str, Any]] = []
    for candidate in metadata:
        candidate_type = str(candidate.get("type", ""))
        candidate_role = str(candidate.get("role", ""))
        candidate_signature = _signature_key(candidate.get("geometry_signature"))

        selected_index: int | None = None
        if candidate_signature is not None:
            signature_matches = [
                index
                for index in unmatched
                if _signature_key(manifest_features[index].get("geometry_signature")) == candidate_signature
                and str(manifest_features[index].get("type")) == candidate_type
            ]
            if len(signature_matches) == 1:
                selected_index = signature_matches[0]

        if selected_index is None:
            typed_matches = [
                index
                for index in unmatched
                if str(manifest_features[index].get("type")) == candidate_type
                and str(manifest_features[index].get("role")) == candidate_role
            ]
            if len(typed_matches) == 1:
                selected_index = typed_matches[0]

        if selected_index is None and len(metadata) == len(manifest_features) == 1:
            if str(manifest_features[0].get("type")) == candidate_type:
                selected_index = 0

        if selected_index is None:
            raise AmgRealTrainingError("label_matching_failed", "candidate could not be matched to manifest feature", sample.sample_dir)
        unmatched.remove(selected_index)
        matches.append(manifest_features[selected_index])

    if unmatched:
        raise AmgRealTrainingError("label_matching_failed", "manifest features were not matched to candidates", sample.sample_dir)
    return matches


def _target_h_values(controls: Mapping[str, Any]) -> tuple[list[float], list[bool]]:
    values: list[float] = []
    for key in ("edge_target_length_mm", "bend_target_length_mm", "flange_target_length_mm"):
        if key in controls:
            values.append(max(float(controls[key]), 1.0e-6))
    values = values[:2]
    mask = [True] * len(values)
    while len(values) < 2:
        values.append(1.0)
        mask.append(False)
    return values, mask


def _target_divisions(controls: Mapping[str, Any]) -> tuple[list[float], list[bool]]:
    values: list[float] = []
    for key in ("circumferential_divisions", "end_arc_divisions", "washer_rings", "bend_rows", "min_elements_across_width"):
        if key in controls:
            values.append(max(float(controls[key]), 1.0))
    values = values[:3]
    mask = [True] * len(values)
    while len(values) < 3:
        values.append(1.0)
        mask.append(False)
    return values, mask


def build_manifest_supervision_targets(samples: Sequence[AmgDatasetSample], batch: GraphBatch | None = None) -> ManifestSupervisionTargets:
    """Build supervised targets from AMG manifests, never from graph target columns."""

    sample_list = list(samples)
    if not sample_list:
        raise AmgRealTrainingError("empty_real_dataset", "at least one sample is required")
    if batch is None:
        batch = build_graph_batch(sample_list)

    part_targets: list[int] = []
    feature_type_targets: list[int] = []
    feature_action_targets: list[int] = []
    log_h_targets: list[list[float]] = []
    log_h_mask: list[list[bool]] = []
    division_targets: list[list[float]] = []
    division_mask: list[list[bool]] = []
    manifest_feature_count = 0
    matched_feature_count = 0

    for sample in sample_list:
        part_class = str(sample.manifest.manifest.get("part", {}).get("part_class"))
        if part_class not in PART_CLASSES:
            raise AmgRealTrainingError("unknown_part_class", f"unsupported part_class: {part_class}", sample.manifest.manifest_path)
        part_targets.append(PART_CLASSES.index(part_class))

        matches = _match_manifest_features(sample)
        manifest_feature_count += len(sample.manifest.manifest.get("features", []))
        matched_feature_count += len(matches)
        for feature in matches:
            feature_type = str(feature.get("type"))
            action = str(feature.get("action"))
            if feature_type not in FEATURE_TYPES:
                raise AmgRealTrainingError("unknown_feature_type", f"unsupported feature type: {feature_type}", sample.manifest.manifest_path)
            if action not in ACTION_NAMES:
                raise AmgRealTrainingError("unknown_feature_action", f"unsupported feature action: {action}", sample.manifest.manifest_path)
            controls = feature.get("controls", {})
            if not isinstance(controls, Mapping):
                raise AmgRealTrainingError("malformed_manifest_controls", "feature controls must be an object", sample.manifest.manifest_path)
            feature_type_targets.append(FEATURE_TYPES.index(feature_type))
            action_index = ACTION_NAMES.index(action)
            feature_action_targets.append(action_index)
            h_values, h_mask = _target_h_values(controls)
            div_values, div_mask = _target_divisions(controls)
            log_h_targets.append([math.log(value) for value in h_values])
            log_h_mask.append(h_mask)
            division_targets.append(div_values)
            division_mask.append(div_mask)

    device = batch.part_features.device
    action_targets = torch.tensor(feature_action_targets, dtype=torch.long, device=device)
    if action_targets.numel() != batch.action_mask.shape[0]:
        raise AmgRealTrainingError("target_count_mismatch", "manifest targets must match feature candidate rows")
    if not batch.action_mask.gather(1, action_targets.view(-1, 1)).all():
        raise AmgRealTrainingError("target_action_not_allowed", "manifest action target is not allowed by graph action mask")

    return ManifestSupervisionTargets(
        part_class_targets=torch.tensor(part_targets, dtype=torch.long, device=device),
        feature_type_targets=torch.tensor(feature_type_targets, dtype=torch.long, device=device),
        feature_action_targets=action_targets,
        log_h_targets=torch.tensor(log_h_targets, dtype=torch.float32, device=device),
        log_h_mask=torch.tensor(log_h_mask, dtype=torch.bool, device=device),
        division_targets=torch.tensor(division_targets, dtype=torch.float32, device=device),
        division_mask=torch.tensor(division_mask, dtype=torch.bool, device=device),
        quality_risk_targets=torch.zeros((len(feature_action_targets), 1), dtype=torch.float32, device=device),
        matched_feature_count=matched_feature_count,
        manifest_feature_count=manifest_feature_count,
        candidate_count=len(feature_action_targets),
    )


def _masked_smooth_l1(prediction: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    if mask.any():
        return F.smooth_l1_loss(prediction[mask], target[mask])
    return prediction.sum() * 0.0


def compute_manifest_supervised_loss(output: AmgModelOutput, targets: ManifestSupervisionTargets) -> RealLossBreakdown:
    """Compute supervised AMG loss from manifest labels."""

    masked_action_logits = apply_action_mask(output.feature_action_logits, output.action_mask)
    part_class_loss = F.cross_entropy(output.part_class_logits, targets.part_class_targets)
    feature_type_loss = F.cross_entropy(output.feature_type_logits, targets.feature_type_targets)
    feature_action_loss = F.cross_entropy(masked_action_logits, targets.feature_action_targets)
    log_h_loss = _masked_smooth_l1(output.log_h, targets.log_h_targets, targets.log_h_mask)
    division_loss = _masked_smooth_l1(output.division_values, targets.division_targets, targets.division_mask)
    quality_risk_loss = F.binary_cross_entropy_with_logits(output.quality_risk_logits, targets.quality_risk_targets)
    total = part_class_loss + feature_type_loss + feature_action_loss + log_h_loss + division_loss + quality_risk_loss
    if not torch.isfinite(total):
        raise AmgRealTrainingError("non_finite_loss", "real supervised loss must be finite")
    return RealLossBreakdown(
        total=total,
        part_class=part_class_loss,
        feature_type=feature_type_loss,
        feature_action=feature_action_loss,
        log_h=log_h_loss,
        division=division_loss,
        quality_risk=quality_risk_loss,
    )


def _split_samples(dataset_root: Path, samples: list[AmgDatasetSample]) -> tuple[list[AmgDatasetSample], list[AmgDatasetSample], str]:
    by_id = {sample.sample_id: sample for sample in samples}
    train_path = dataset_root / "splits" / "train.txt"
    val_path = dataset_root / "splits" / "val.txt"
    if train_path.is_file() and val_path.is_file():
        train_ids = [line.strip() for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        val_ids = [line.strip() for line in val_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if train_ids and val_ids:
            return [by_id[sample_id] for sample_id in train_ids], [by_id[sample_id] for sample_id in val_ids], "dataset_splits"

    ordered = sorted(samples, key=lambda item: item.sample_id)
    split_index = max(1, int(0.80 * len(ordered)))
    if split_index >= len(ordered):
        split_index = len(ordered) - 1
    return ordered[:split_index], ordered[split_index:], "deterministic_80_20_fallback"


def _batch_slices(samples: list[AmgDatasetSample], batch_size: int) -> list[list[AmgDatasetSample]]:
    if batch_size <= 0:
        raise AmgRealTrainingError("invalid_batch_size", "batch_size must be positive")
    return [samples[index : index + batch_size] for index in range(0, len(samples), batch_size)]


def _evaluate(model: AmgGraphModel, samples: list[AmgDatasetSample], batch_size: int, prefix: str) -> dict[str, float]:
    losses: list[RealLossBreakdown] = []
    with torch.no_grad():
        for batch_samples in _batch_slices(samples, batch_size):
            batch = build_graph_batch(batch_samples)
            targets = build_manifest_supervision_targets(batch_samples, batch)
            losses.append(compute_manifest_supervised_loss(model(batch), targets))
    if not losses:
        raise AmgRealTrainingError("empty_split", f"{prefix} split must not be empty")
    return {
        key: sum(item.as_metrics(prefix)[key] for item in losses) / len(losses)
        for key in losses[0].as_metrics(prefix)
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_real_dataset_training(config: RealTrainingConfig) -> RealTrainingResult:
    """Train the AMG model on real ANSA-accepted manifest labels."""

    if config.epochs <= 0:
        raise AmgRealTrainingError("invalid_epochs", "epochs must be positive")
    torch.manual_seed(config.seed)
    random.seed(config.seed)

    samples = validate_real_training_dataset(config.dataset_root)
    train_samples, val_samples, split_source = _split_samples(config.dataset_root, samples)
    if not train_samples or not val_samples:
        raise AmgRealTrainingError("empty_split", "train and validation splits must both contain samples")

    first_batch = build_graph_batch(train_samples[:1])
    model = AmgGraphModel(ModelDimensions(part_feature_dim=first_batch.part_features.shape[1], hidden_dim=config.hidden_dim))
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)

    rng = random.Random(config.seed)
    last_train_metrics: dict[str, float] = {}
    for _epoch in range(1, config.epochs + 1):
        shuffled = list(train_samples)
        rng.shuffle(shuffled)
        model.train()
        train_losses: list[RealLossBreakdown] = []
        for batch_samples in _batch_slices(shuffled, config.batch_size):
            batch = build_graph_batch(batch_samples)
            targets = build_manifest_supervision_targets(batch_samples, batch)
            optimizer.zero_grad(set_to_none=True)
            breakdown = compute_manifest_supervised_loss(model(batch), targets)
            breakdown.total.backward()
            optimizer.step()
            train_losses.append(breakdown)
        if not train_losses:
            raise AmgRealTrainingError("empty_split", "train split must not be empty")
        last_train_metrics = {
            key: sum(item.as_metrics("train")[key] for item in train_losses) / len(train_losses)
            for key in train_losses[0].as_metrics("train")
        }

    model.eval()
    val_metrics = _evaluate(model, val_samples, config.batch_size, "val")
    all_batch = build_graph_batch(samples)
    all_targets = build_manifest_supervision_targets(samples, all_batch)
    label_coverage = float(all_targets.matched_feature_count / max(1, all_targets.manifest_feature_count))

    config.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config.output_dir / "checkpoint.pt"
    metrics_path = config.output_dir / "metrics.json"
    training_config_path = config.output_dir / "training_config.json"
    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "epochs": config.epochs,
            "metrics_path": metrics_path.as_posix(),
        },
        checkpoint_path,
    )
    config_payload = {
        "dataset_root": config.dataset_root.as_posix(),
        "output_dir": config.output_dir.as_posix(),
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "seed": config.seed,
        "learning_rate": config.learning_rate,
        "hidden_dim": config.hidden_dim,
    }
    metrics: dict[str, Any] = {
        "status": "SUCCESS",
        "dataset_root": config.dataset_root.as_posix(),
        "sample_count": len(samples),
        "train_sample_count": len(train_samples),
        "validation_sample_count": len(val_samples),
        "candidate_count": all_targets.candidate_count,
        "manifest_feature_count": all_targets.manifest_feature_count,
        "matched_target_count": all_targets.matched_feature_count,
        "label_coverage_ratio": label_coverage,
        "split_source": split_source,
        "epochs": config.epochs,
        "seed": config.seed,
        "checkpoint_path": checkpoint_path.as_posix(),
    }
    metrics.update(last_train_metrics)
    metrics.update(val_metrics)
    _write_json(training_config_path, config_payload)
    _write_json(metrics_path, metrics)
    return RealTrainingResult(
        checkpoint_path=checkpoint_path.as_posix(),
        metrics_path=metrics_path.as_posix(),
        training_config_path=training_config_path.as_posix(),
        metrics=metrics,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train AMG on real ANSA-accepted CDF manifest labels.")
    parser.add_argument("--dataset", required=True, help="CDF dataset root")
    parser.add_argument("--out", required=True, help="training output directory")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=1.0e-3)
    parser.add_argument("--hidden-dim", type=int, default=32)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_real_dataset_training(
            RealTrainingConfig(
                dataset_root=Path(args.dataset),
                output_dir=Path(args.out),
                epochs=args.epochs,
                batch_size=args.batch_size,
                seed=args.seed,
                learning_rate=args.learning_rate,
                hidden_dim=args.hidden_dim,
            )
        )
    except AmgRealTrainingError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": "SUCCESS", **result.metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
