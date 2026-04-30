from __future__ import annotations

import torch

from cae_mesh_common.graph.hetero_graph import HeteroGraph
from training_pipeline.data.dataset import PART_STRATEGY_CLASSES
from training_pipeline.data.normalization import normalize_graph_batch
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet


def predict_recipe_signals(model: dict, graph: HeteroGraph, assembly: dict) -> dict:
    neural_net = _build_model(model)
    graph_batch = normalize_graph_batch(graph.to_torch_dict(), model["node_feature_stats"])
    with torch.no_grad():
        outputs = neural_net(graph_batch)

    part_nodes = graph.node_sets["part"]
    part_strategy_logits = outputs["part_strategy"]
    normalized_size = outputs["size_field"].squeeze(-1)
    pred_sizes = torch.clamp(normalized_size * float(model["target_std"]) + float(model["target_mean"]), min=2.0)
    confidences = _part_confidences(model, outputs)

    part_strategies = []
    size_fields = []
    for index, node in enumerate(part_nodes):
        predicted_strategy = _class_name(part_strategy_logits[index], model, "part_strategy", PART_STRATEGY_CLASSES)
        part_strategies.append(
            {
                "part_uid": node["uid"],
                "strategy": predicted_strategy,
                "geometry_hint_strategy": _assembly_strategy_hint(assembly, node["uid"]),
                "confidence": confidences[index],
            }
        )
        size_fields.append(
            {
                "part_uid": node["uid"],
                "target_size": round(float(pred_sizes[index].item()), 4),
                "confidence": confidences[index],
            }
        )

    return {
        "base_size": round(float(torch.mean(pred_sizes).item()), 4),
        "part_strategies": part_strategies,
        "size_fields": size_fields,
        "connections": assembly.get("connections", []),
        "confidence": round(sum(confidences) / len(confidences), 4),
        "neural_outputs": {
            "part_strategy_logits": part_strategy_logits.tolist(),
            "face_semantic_logits": outputs["face_semantic"].tolist(),
            "edge_semantic_logits": outputs["edge_semantic"].tolist(),
            "connection_candidate_logits": outputs["connection_candidate"].tolist(),
            "failure_risk": outputs["failure_risk"].squeeze(-1).tolist(),
            "repair_action_logits": outputs["repair_action"].tolist(),
            "predicted_part_strategy": [item["strategy"] for item in part_strategies],
        },
    }


def _build_model(artifact: dict) -> BRepAssemblyNet:
    model = BRepAssemblyNet(
        node_input_dims={key: int(value) for key, value in artifact["node_input_dims"].items()},
        edge_types=list(artifact["edge_types"]),
        hidden_dim=int(artifact["hidden_dim"]),
        num_layers=int(artifact["num_layers"]),
    )
    model.load_state_dict({key: torch.as_tensor(value) for key, value in artifact["state_dict"].items()})
    model.eval()
    return model


def _part_confidences(artifact: dict, outputs: dict[str, torch.Tensor]) -> list[float]:
    part_conf = torch.softmax(outputs["part_strategy"], dim=1).max(dim=1).values
    repair_conf = torch.softmax(outputs["repair_action"], dim=1).max(dim=1).values
    risk_conf = 1.0 - torch.abs(outputs["failure_risk"].squeeze(-1) - 0.5) * 0.5
    trained = float(artifact.get("confidence", 0.5))
    combined = 0.35 * part_conf + 0.25 * repair_conf + 0.20 * risk_conf + 0.20 * trained
    return [round(max(0.05, min(0.99, float(value))), 4) for value in combined]


def _class_name(logits: torch.Tensor, artifact: dict, head: str, default_classes: list[str]) -> str:
    heads = artifact.get("heads", {})
    classes = heads.get(head, default_classes) if isinstance(heads, dict) else default_classes
    if not isinstance(classes, list) or not classes:
        classes = default_classes
    index = int(torch.argmax(logits).item())
    return str(classes[min(index, len(classes) - 1)])


def _assembly_strategy_hint(assembly: dict, part_uid: str) -> str:
    for part in assembly.get("parts", []):
        if part["part_uid"] == part_uid:
            return str(part.get("strategy", "unknown"))
    raise ValueError(f"graph part {part_uid} is not present in assembly")
