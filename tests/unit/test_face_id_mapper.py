from __future__ import annotations

from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.cad.face_id_mapper import map_reimported_faces


def test_face_matching_keeps_ids_for_identical_signatures():
    assembly = AssemblyGrammar(123).generate(0)
    source = assembly["face_signatures"]
    mapping = map_reimported_faces(source, list(source))
    assert len(mapping) == len(source)
