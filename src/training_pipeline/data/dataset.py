from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import torch
from torch.utils.data import Dataset

from cae_mesh_common.graph.hetero_graph import HeteroGraph, load_graph
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index
from cae_dataset_factory.dataset.split_builder import read_split


PART_STRATEGY_CLASSES = ["shell", "solid", "mass_only", "connector"]
FACE_SEMANTIC_CLASSES = ["structural", "side_wall", "contact", "load", "review"]
EDGE_SEMANTIC_CLASSES = ["boundary_edge", "feature_edge", "connection_edge", "short_edge"]
CONNECTION_CLASSES = ["reject", "keep"]
REPAIR_ACTION_CLASSES = ["none", "local_remesh", "preserve_connection_hole", "manual_review"]
FEATURE_REFINEMENT_CLASSES = ["none", "hole", "thin_region", "rib_root", "boss", "contact", "boundary", "curvature", "short_edge"]


class BRepAssemblyDataset(Dataset):
    """Torch dataset backed by generated CDF heterogeneous graph artifacts."""

    def __init__(self, dataset_dir: Path | str, split: str = "train") -> None:
        self.dataset_dir = Path(dataset_dir)
        self.rows = list(_split_rows(self.dataset_dir, split).to_dict("records"))

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, object]:
        row = self.rows[index]
        graph = load_graph(row["graph_path"])
        labels = json.loads(Path(row["label_json_path"]).read_text(encoding="utf-8"))
        targets = build_graph_targets(graph, labels)
        return {
            "sample_id": str(row["sample_id"]),
            "graph": graph.to_torch_dict(),
            "graph_path": str(row["graph_path"]),
            **targets,
        }


def build_graph_targets(graph: HeteroGraph, labels: dict[str, Any]) -> dict[str, torch.Tensor]:
    part_labels = _map_by_uid(labels["part_labels"], "part_uid")
    face_labels = _map_by_uid(labels["face_labels"], "face_uid")
    edge_labels = _map_by_uid(labels["edge_labels"], "edge_uid")
    mesh_size_labels = labels.get("mesh_size_labels")
    if not mesh_size_labels:
        mesh_size_labels = _legacy_mesh_size_labels(labels.get("size_field_labels", []))
    size_by_type = _mesh_size_by_type(mesh_size_labels)
    risk_labels = _map_by_uid(labels["failure_risks"], "part_uid")
    connection_labels = _map_by_uid(labels["connection_labels"], "connection_uid")
    repair_by_part = {node["uid"]: "none" for node in graph.node_sets["part"]}
    for repair in labels.get("repair_actions", []):
        target_uid = repair["target_uid"]
        if target_uid not in repair_by_part:
            raise ValueError(f"repair action references unknown part node: {target_uid}")
        repair_by_part[target_uid] = repair["action"]

    return {
        "part_strategy": torch.as_tensor(
            [_class_index(_require(part_labels, node["uid"], "part_strategy")["strategy"], PART_STRATEGY_CLASSES) for node in graph.node_sets["part"]],
            dtype=torch.long,
        ),
        "face_semantic": torch.as_tensor(
            [_class_index(_require(face_labels, node["uid"], "face_semantic")["semantic"], FACE_SEMANTIC_CLASSES) for node in graph.node_sets["face"]],
            dtype=torch.long,
        ),
        "edge_semantic": torch.as_tensor(
            [_class_index(_require(edge_labels, node["uid"], "edge_semantic")["semantic"], EDGE_SEMANTIC_CLASSES) for node in graph.node_sets["edge"]],
            dtype=torch.long,
        ),
        "part_size": _size_tensor(size_by_type, "part", [node["uid"] for node in graph.node_sets["part"]], "part_size"),
        "size_field": _size_tensor(size_by_type, "part", [node["uid"] for node in graph.node_sets["part"]], "part_size"),
        "face_size": _size_tensor(size_by_type, "face", [node["uid"] for node in graph.node_sets["face"]], "face_size"),
        "edge_size": _size_tensor(size_by_type, "edge", [node["uid"] for node in graph.node_sets["edge"]], "edge_size"),
        "contact_size": _size_tensor(
            size_by_type,
            "contact_candidate",
            [node["uid"] for node in graph.node_sets["contact_candidate"]],
            "contact_size",
        ),
        "feature_refinement_class": torch.as_tensor(
            [
                _class_index(
                    _require(size_by_type.get("face", {}), node["uid"], "feature_refinement_class").get("refinement_class", "none"),
                    FEATURE_REFINEMENT_CLASSES,
                )
                for node in graph.node_sets["face"]
            ],
            dtype=torch.long,
        ),
        "failure_risk": torch.as_tensor(
            [float(_require(risk_labels, node["uid"], "failure_risk")["risk"]) for node in graph.node_sets["part"]],
            dtype=torch.float32,
        ),
        "connection_candidate": torch.as_tensor(
            [
                1 if bool(_require(connection_labels, node["connection_uid"], "connection_candidate")["keep"]) else 0
                for node in graph.node_sets["contact_candidate"]
            ],
            dtype=torch.long,
        ),
        "repair_action": torch.as_tensor(
            [_class_index(repair_by_part[node["uid"]], REPAIR_ACTION_CLASSES) for node in graph.node_sets["part"]],
            dtype=torch.long,
        ),
    }


def _split_rows(dataset_dir: Path, split: str):
    index = read_dataset_index(dataset_dir)
    sample_ids = set(read_split(dataset_dir, split))
    return index[index["sample_id"].isin(sample_ids)] if sample_ids else index


def _map_by_uid(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for record in records:
        uid = record[key]
        if uid in result:
            raise ValueError(f"duplicate label for {key}={uid}")
        result[uid] = record
    return result


def _mesh_size_by_type(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        target_type = str(record["target_type"])
        target_uid = str(record["target_uid"])
        result.setdefault(target_type, {})
        if target_uid in result[target_type]:
            existing = result[target_type][target_uid]
            if bool(record.get("required", False)) and not bool(existing.get("required", False)):
                result[target_type][target_uid] = record
            elif float(record.get("target_size_mm", 0.0)) < float(existing.get("target_size_mm", 0.0)):
                result[target_type][target_uid] = record
        else:
            result[target_type][target_uid] = record
    return result


def _size_tensor(size_by_type: dict[str, dict[str, dict[str, Any]]], target_type: str, uids: list[str], label_name: str) -> torch.Tensor:
    mapping = size_by_type.get(target_type, {})
    return torch.as_tensor(
        [float(_require(mapping, uid, label_name)["target_size_mm"]) for uid in uids],
        dtype=torch.float32,
    )


def _legacy_mesh_size_labels(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "target_uid": record["part_uid"],
            "target_type": "part",
            "source_feature_type": "legacy_part_size",
            "target_size_mm": record["target_size"],
            "min_size_mm": max(0.25, float(record["target_size"]) * 0.55),
            "max_size_mm": max(float(record["target_size"]), float(record["target_size"]) * 1.75),
            "refinement_reason": "legacy_part_size",
            "refinement_class": "none",
            "required": True,
            "confidence_source": "legacy_size_field_labels",
        }
        for record in records
    ]


def _require(mapping: dict[str, dict[str, Any]], uid: str, label_name: str) -> dict[str, Any]:
    if uid not in mapping:
        raise ValueError(f"missing {label_name} label for graph node {uid}")
    return mapping[uid]


def _class_index(value: str, classes: list[str]) -> int:
    if value not in classes:
        raise ValueError(f"unknown class {value!r}; expected one of {classes}")
    return classes.index(value)
