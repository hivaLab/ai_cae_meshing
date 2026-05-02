from __future__ import annotations

import random
from typing import Any

from cae_mesh_common.cad.topology import transform_identity
from cae_dataset_factory.assembly.connection_synthesizer import synthesize_screw_connections
from cae_dataset_factory.cad.templates.bracket import BracketTemplate
from cae_dataset_factory.cad.templates.motor_dummy import MotorDummyTemplate
from cae_dataset_factory.cad.templates.pcb_dummy import PcbDummyTemplate
from cae_dataset_factory.cad.templates.plastic_base import PlasticBaseTemplate
from cae_dataset_factory.cad.templates.ribbed_cover import RibbedCoverTemplate
from cae_dataset_factory.cad.templates.screw import ScrewTemplate
from cae_dataset_factory.cad.templates.sheet_metal_box import SheetMetalBoxTemplate


MATERIAL_LIBRARY = {
    "materials": [
        {"material_id": "MAT_STEEL", "name": "Steel", "young_modulus": 210000.0, "poisson_ratio": 0.3, "density": 7.85e-9},
        {"material_id": "MAT_ABS", "name": "ABS Plastic", "young_modulus": 2400.0, "poisson_ratio": 0.36, "density": 1.05e-9},
        {"material_id": "MAT_ALUMINUM", "name": "Aluminum", "young_modulus": 70000.0, "poisson_ratio": 0.33, "density": 2.7e-9},
        {"material_id": "MAT_PCB", "name": "PCB Equivalent", "young_modulus": 18000.0, "poisson_ratio": 0.22, "density": 1.8e-9},
    ]
}


class AssemblyGrammar:
    def __init__(self, seed: int) -> None:
        self.seed = seed

    def generate(self, sample_index: int) -> dict[str, Any]:
        sample_id = f"sample_{sample_index:06d}"
        rng = random.Random(self.seed + sample_index)
        family_name, template_plan = _template_family(sample_index)
        parts = []
        face_signatures = []
        for index, template in enumerate(template_plan):
            part = template.generate(f"{sample_id}_part_{index:02d}", rng)
            payload = part.to_dict()
            payload["name"] = f"{template.name}_{index:02d}"
            parts.append(payload)
            face_signatures.extend(payload["face_signatures"])
        product_tree = {
            "assembly_id": sample_id,
            "root_part_uid": parts[0]["part_uid"],
            "parts": [
                {
                    "part_uid": part["part_uid"],
                    "name": part["name"],
                    "parent_uid": None if index == 0 else parts[0]["part_uid"],
                    "transform": transform_identity(),
                }
                for index, part in enumerate(parts)
            ],
        }
        connections = synthesize_screw_connections(parts)
        return {
            "sample_id": sample_id,
            "topology_family": family_name,
            "schema_version": "0.1.0",
            "units": "mm",
            "parts": parts,
            "product_tree": product_tree,
            "material_library": MATERIAL_LIBRARY,
            "connections": connections,
            "boundary_named_sets": {"fixed_support": [parts[0]["part_uid"]], "load_faces": [parts[1]["part_uid"]]},
            "face_signatures": face_signatures,
        }


def _template_family(sample_index: int):
    families = [
        (
            "appliance_shell_assembly",
            [
                PlasticBaseTemplate(),
                RibbedCoverTemplate(),
                SheetMetalBoxTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                SheetMetalBoxTemplate(),
                PcbDummyTemplate(),
                MotorDummyTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
            ],
        ),
        (
            "thin_sheet_bracket_frame",
            [
                SheetMetalBoxTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                PcbDummyTemplate(),
            ],
        ),
        (
            "ribbed_plastic_cover_stack",
            [
                PlasticBaseTemplate(),
                RibbedCoverTemplate(),
                RibbedCoverTemplate(),
                BracketTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
            ],
        ),
        (
            "cylindrical_housing_support",
            [
                SheetMetalBoxTemplate(),
                MotorDummyTemplate(),
                MotorDummyTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                PcbDummyTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
            ],
        ),
        (
            "furniture_like_frame",
            [
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                BracketTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
            ],
        ),
        (
            "box_enclosure_module",
            [
                SheetMetalBoxTemplate(),
                SheetMetalBoxTemplate(),
                SheetMetalBoxTemplate(),
                PlasticBaseTemplate(),
                RibbedCoverTemplate(),
                PcbDummyTemplate(),
                MotorDummyTemplate(),
                ScrewTemplate(),
                ScrewTemplate(),
            ],
        ),
    ]
    family_name, templates = families[sample_index % len(families)]
    variant = (sample_index // len(families)) % 6
    templates = list(templates)
    for index in range(variant):
        if index % 3 == 0:
            templates.append(ScrewTemplate())
        elif index % 3 == 1:
            templates.append(BracketTemplate())
        else:
            templates.append(SheetMetalBoxTemplate())
    return f"{family_name}_v{variant}", templates
