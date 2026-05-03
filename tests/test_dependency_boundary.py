from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_sources(*roots: str) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        result.extend((ROOT / root).rglob("*.py"))
    return result


def test_packages_import_with_empty_modules() -> None:
    import ai_mesh_generator
    import cad_dataset_factory

    assert ai_mesh_generator.__version__
    assert cad_dataset_factory.__version__


def test_readme_agent_docs_remain_at_repository_root() -> None:
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "AGENT.md").is_file()


def test_no_amg_import_in_cdf() -> None:
    forbidden = ["import amg", "from amg", "import ai_mesh_generator", "from ai_mesh_generator"]
    for path in python_sources("cad_dataset_factory"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"AMG dependency found in {path}: {token}"


def test_ansa_import_scope() -> None:
    allowed_parts = ("ansa_scripts",)
    forbidden = ["import ansa", "from ansa"]
    for path in python_sources("cad_dataset_factory", "ai_mesh_generator"):
        if any(part in path.parts for part in allowed_parts):
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"ANSA API import outside ANSA script in {path}"


def test_graph_schema_has_no_target_action_column() -> None:
    graph_schema = (ROOT / "contracts" / "AMG_BREP_GRAPH_SM_V1.schema.json").read_text(encoding="utf-8")
    forbidden = [
        "target_action_id",
        "target_edge_length_mm",
        "circumferential_divisions",
        "washer_rings",
        "bend_rows",
    ]
    for token in forbidden:
        assert token not in graph_schema
