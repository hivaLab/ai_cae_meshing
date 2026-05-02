from __future__ import annotations

from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.labeling.mesh_size_oracle import mesh_size_labels


def test_feature_refinement_labels_are_smaller_than_part_baseline():
    assembly = AssemblyGrammar(20260430).generate(0)
    labels = mesh_size_labels(assembly)
    part_sizes = {item["target_uid"]: item["target_size_mm"] for item in labels if item["target_type"] == "part"}
    refined = [
        item
        for item in labels
        if item["target_type"] in {"face", "edge", "feature", "contact_candidate"}
        and item["refinement_reason"]
        in {
            "hole_or_boss_refinement",
            "rib_root_refinement",
            "thin_region_refinement",
            "feature_edge_refinement",
            "contact_or_connection_refinement",
        }
    ]

    assert refined
    for item in refined:
        owning_part = _owning_part_uid(assembly, item)
        if owning_part:
            assert item["target_size_mm"] < part_sizes[owning_part]
        assert item["required"] is True


def test_mesh_size_labels_cover_graph_targets_and_allowed_types():
    assembly = AssemblyGrammar(20260430).generate(3)
    labels = mesh_size_labels(assembly)
    target_types = {item["target_type"] for item in labels}

    assert {"part", "face", "edge", "feature", "contact_candidate", "connection"} <= target_types
    assert all(item["target_size_mm"] <= item["max_size_mm"] for item in labels)
    assert all(item["min_size_mm"] <= item["target_size_mm"] for item in labels)


def _owning_part_uid(assembly: dict, label: dict) -> str | None:
    target = label["target_uid"]
    for part in assembly["parts"]:
        if target == part["part_uid"]:
            return part["part_uid"]
        if any(target == face["face_uid"] for face in part.get("face_signatures", [])):
            return part["part_uid"]
        if any(target == feature["feature_uid"] for feature in part.get("features", [])):
            return part["part_uid"]
        if target.startswith(f"{part['part_uid']}_edge_"):
            return part["part_uid"]
    if label["target_type"] in {"contact_candidate", "connection"}:
        return None
    return None
