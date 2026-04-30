from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from training_pipeline.evaluate import build_model_from_artifact


def export_model(model: Path | str, output: Path | str) -> Path:
    artifact = torch.load(Path(model), map_location="cpu", weights_only=False)
    _validate_artifact(artifact)
    neural_net = build_model_from_artifact(artifact)
    exported = {
        "model_id": artifact["model_id"],
        "model_type": artifact["model_type"],
        "framework": "torch",
        "export_format": "amg_deployment_artifact_v1",
        "node_input_dims": artifact["node_input_dims"],
        "node_feature_names": artifact["node_feature_names"],
        "edge_types": artifact["edge_types"],
        "hidden_dim": artifact["hidden_dim"],
        "num_layers": artifact["num_layers"],
        "node_feature_stats": artifact["node_feature_stats"],
        "target_mean": artifact["target_mean"],
        "target_std": artifact["target_std"],
        "heads": artifact["heads"],
        "metrics": artifact.get("metrics", {}),
        "confidence": artifact.get("confidence", 0.0),
        "state_dict": {key: value.detach().cpu() for key, value in neural_net.state_dict().items()},
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(exported, output)
    manifest = {key: value for key, value in exported.items() if key != "state_dict"}
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def _validate_artifact(artifact: dict) -> None:
    required = {
        "model_id",
        "model_type",
        "framework",
        "node_input_dims",
        "node_feature_names",
        "edge_types",
        "hidden_dim",
        "num_layers",
        "node_feature_stats",
        "target_mean",
        "target_std",
        "heads",
        "state_dict",
    }
    missing = required - set(artifact)
    if missing:
        raise ValueError(f"cannot export invalid B-Rep Assembly Net artifact, missing {sorted(missing)}")
    if artifact["model_type"] != "hetero_brep_assembly_net" or artifact["framework"] != "torch":
        raise ValueError("export_model only accepts real torch heterogeneous B-Rep Assembly Net artifacts")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export-amg-model")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    print(export_model(args.model, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
