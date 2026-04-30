from __future__ import annotations

from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar


def test_assembly_has_at_least_ten_parts_and_connections():
    assembly = AssemblyGrammar(123).generate(0)
    assert len(assembly["parts"]) >= 10
    assert assembly["connections"]
    assert assembly["product_tree"]["assembly_id"] == "sample_000000"
