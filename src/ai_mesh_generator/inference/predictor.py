from __future__ import annotations

import torch

from cae_mesh_common.graph.hetero_graph import HeteroGraph
from training_pipeline.data.dataset import FEATURE_REFINEMENT_CLASSES, PART_STRATEGY_CLASSES
from training_pipeline.data.normalization import normalize_graph_batch
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet


def predict_recipe_signals(model: dict, graph: HeteroGraph, assembly: dict) -> dict:
    neural_net = _build_model(model)
    graph_batch = normalize_graph_batch(graph.to_torch_dict(), model["node_feature_stats"])
    with torch.no_grad():
        outputs = neural_net(graph_batch)

    part_nodes = graph.node_sets["part"]
    part_strategy_logits = outputs["part_strategy"]
    normalized_size = outputs["part_size"].squeeze(-1)
    pred_sizes = torch.clamp(normalized_size * float(model["target_std"]) + float(model["target_mean"]), min=2.0)
    face_sizes = _denormalized_size(outputs["face_size"], model)
    edge_sizes = _denormalized_size(outputs["edge_size"], model)
    contact_sizes = _denormalized_size(outputs["contact_size"], model)
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

    refinement_zones = _predicted_refinement_zones(graph, outputs, face_sizes, edge_sizes, contact_sizes)
    return {
        "base_size": round(float(torch.mean(pred_sizes).item()), 4),
        "part_strategies": part_strategies,
        "size_fields": size_fields,
        "refinement_zones": refinement_zones,
        "connections": assembly.get("connections", []),
        "confidence": round(sum(confidences) / len(confidences), 4),
        "neural_outputs": {
            "part_strategy_logits": part_strategy_logits.tolist(),
            "face_semantic_logits": outputs["face_semantic"].tolist(),
            "edge_semantic_logits": outputs["edge_semantic"].tolist(),
            "feature_refinement_class_logits": outputs["feature_refinement_class"].tolist(),
            "face_size": face_sizes.tolist(),
            "edge_size": edge_sizes.tolist(),
            "contact_size": contact_sizes.tolist(),
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


def _denormalized_size(values: torch.Tensor, artifact: dict) -> torch.Tensor:
    return torch.clamp(values.squeeze(-1) * float(artifact["target_std"]) + float(artifact["target_mean"]), min=0.5)


def _predicted_refinement_zones(
    graph: HeteroGraph,
    outputs: dict[str, torch.Tensor],
    face_sizes: torch.Tensor,
    edge_sizes: torch.Tensor,
    contact_sizes: torch.Tensor,
) -> list[dict]:
    zones = []
    face_classes = torch.argmax(outputs["feature_refinement_class"], dim=1)
    face_confidences = torch.softmax(outputs["feature_refinement_class"], dim=1).max(dim=1).values
    for index, node in enumerate(graph.node_sets["face"]):
        cls = FEATURE_REFINEMENT_CLASSES[int(face_classes[index].item())]
        zones.append(
            _zone(
                zone_uid=f"ai_face_zone_{node['uid']}",
                target_type="face",
                target_uid=node["uid"],
                size=float(face_sizes[index].item()),
                reason=f"ai_{cls}_face_refinement",
                control_type="surface_mesh_size_control",
                preserve_boundary=cls in {"hole", "thin_region", "rib_root", "boss", "contact", "boundary", "curvature"},
                confidence=float(face_confidences[index].item()),
                source_feature_type=cls,
            )
        )
    for index, node in enumerate(graph.node_sets["edge"]):
        zones.append(
            _zone(
                zone_uid=f"ai_edge_zone_{node['uid']}",
                target_type="edge",
                target_uid=node["uid"],
                size=float(edge_sizes[index].item()),
                reason="ai_edge_refinement",
                control_type="edge_length_control",
                preserve_boundary=True,
                confidence=0.75,
                source_feature_type="edge",
            )
        )
    for index, node in enumerate(graph.node_sets["contact_candidate"]):
        zones.append(
            _zone(
                zone_uid=f"ai_contact_zone_{node['uid']}",
                target_type="contact_candidate",
                target_uid=node["uid"],
                size=float(contact_sizes[index].item()),
                reason="ai_contact_or_connection_refinement",
                control_type="contact_surface_size_control",
                preserve_boundary=True,
                confidence=0.85,
                source_feature_type="contact",
            )
        )
    return zones


def _zone(
    *,
    zone_uid: str,
    target_type: str,
    target_uid: str,
    size: float,
    reason: str,
    control_type: str,
    preserve_boundary: bool,
    confidence: float,
    source_feature_type: str,
) -> dict:
    size = round(max(0.5, float(size)), 4)
    return {
        "zone_uid": zone_uid,
        "target_type": target_type,
        "target_uid": target_uid,
        "size_mm": size,
        "min_size_mm": round(max(0.25, size * 0.55), 4),
        "max_size_mm": round(max(size, size * 1.75), 4),
        "growth_rate": 1.25,
        "preserve_boundary": bool(preserve_boundary),
        "ansa_control_type": control_type,
        "reason": reason,
        "source_feature_type": source_feature_type,
        "confidence": round(max(0.05, min(0.99, confidence)), 4),
        "required": bool(preserve_boundary),
    }


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
