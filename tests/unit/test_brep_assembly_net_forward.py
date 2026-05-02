from __future__ import annotations

import torch

from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.dataset.sample_writer import build_oracle_labels
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph
from training_pipeline.data.collate import collate_graph_batch
from training_pipeline.data.dataset import build_graph_targets
from training_pipeline.losses.multitask_loss import multitask_loss
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet


def test_brep_assembly_net_forward_shapes_and_loss():
    item = _graph_item("a", 0)
    batch = collate_graph_batch([item])
    model = _model_for_graph(batch["graph"])
    outputs = model(batch["graph"])

    assert outputs["part_strategy"].shape == (11, 4)
    assert outputs["face_semantic"].shape == (66, 5)
    assert outputs["edge_semantic"].shape == (132, 4)
    assert outputs["connection_candidate"].shape[1] == 2
    assert outputs["size_field"].shape == (11, 1)
    loss = multitask_loss(outputs, batch)
    assert torch.isfinite(loss)


def test_brep_assembly_net_rejects_wrong_node_feature_shape():
    item = _graph_item("a", 0)
    batch = collate_graph_batch([item])
    model = _model_for_graph(batch["graph"])
    bad_graph = dict(batch["graph"])
    bad_graph["node_features"] = dict(batch["graph"]["node_features"])
    bad_graph["node_features"]["part"] = torch.ones(12, 3)
    try:
        model(bad_graph)
    except ValueError as exc:
        assert "part node_features" in str(exc)
    else:
        raise AssertionError("wrong node feature shape should fail explicitly")


def test_collate_graph_batch_offsets_edges_and_concatenates_targets():
    batch = collate_graph_batch([_graph_item("a", 0), _graph_item("b", 1)])
    assert batch["sample_id"] == ["a", "b"]
    assert batch["graph"]["node_features"]["part"].shape[0] == 22
    assert batch["graph"]["node_features"]["face"].shape[0] == 132
    assert batch["part_strategy"].shape == (22,)
    edge_index = batch["graph"]["edge_index"]["part__has_face__face"]
    assert int(edge_index[0].max().item()) == 21
    assert int(edge_index[1].max().item()) == 131


def _graph_item(sample_id: str, sample_index: int) -> dict[str, object]:
    assembly = AssemblyGrammar(20260430).generate(sample_index)
    graph = build_brep_graph(assembly)
    labels = build_oracle_labels(assembly)
    return {
        "sample_id": sample_id,
        "graph_path": f"{sample_id}.pt",
        "graph": graph.to_torch_dict(),
        **build_graph_targets(graph, labels),
    }


def _model_for_graph(graph_batch: dict[str, object]) -> BRepAssemblyNet:
    return BRepAssemblyNet(
        node_input_dims={node_type: int(features.shape[1]) for node_type, features in graph_batch["node_features"].items()},
        edge_types=list(graph_batch["edge_index"]),
        hidden_dim=16,
        num_layers=2,
    )
