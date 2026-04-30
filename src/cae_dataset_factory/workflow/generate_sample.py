from __future__ import annotations

from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.defects.defect_injector import inject_defects


def generate_sample(sample_index: int, seed: int, defect_rate: float) -> dict:
    assembly = AssemblyGrammar(seed).generate(sample_index)
    return inject_defects(assembly, seed + sample_index * 17, defect_rate)
