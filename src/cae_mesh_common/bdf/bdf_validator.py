from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .bdf_reader import BDFModel, _duplicate_ids, read_bdf


@dataclass
class BDFValidationResult:
    parse_success: bool
    missing_property_count: int
    missing_material_count: int
    duplicate_id_count: int
    missing_nodes_count: int
    element_count: int
    shell_element_count: int
    solid_element_count: int
    connector_count: int
    messages: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.parse_success
            and self.missing_property_count == 0
            and self.missing_material_count == 0
            and self.duplicate_id_count == 0
            and self.missing_nodes_count == 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "bdf_parse_success": self.parse_success,
            "missing_property_count": self.missing_property_count,
            "missing_material_count": self.missing_material_count,
            "duplicate_id_count": self.duplicate_id_count,
            "missing_nodes_count": self.missing_nodes_count,
            "element_count": self.element_count,
            "shell_element_count": self.shell_element_count,
            "solid_element_count": self.solid_element_count,
            "connector_count": self.connector_count,
            "passed": self.passed,
            "messages": self.messages,
        }


def validate_model(model: BDFModel) -> BDFValidationResult:
    missing_properties = 0
    missing_materials = 0
    missing_nodes = 0
    messages: list[str] = []
    shell_types = {"CQUAD4", "CTRIA3"}
    solid_types = {"CTETRA", "CTETRA10", "CHEXA", "CPENTA", "CPYRA", "PYRAMID"}
    connector_types = {"RBE2", "RBE3", "CBUSH", "CONM2"}

    for eid, element in model.elements.items():
        etype = str(element["type"])
        pid = element.get("pid")
        if pid is not None:
            if int(pid) not in model.properties:
                missing_properties += 1
                messages.append(f"element {eid} references missing property {pid}")
            else:
                prop = model.properties[int(pid)]
                mid = int(prop.get("mid", 0))
                if mid and mid not in model.materials:
                    missing_materials += 1
                    messages.append(f"property {pid} references missing material {mid}")
        for nid in element.get("nodes", []):
            if int(nid) not in model.nodes and etype not in {"RBE2", "RBE3", "CONM2"}:
                missing_nodes += 1
                messages.append(f"element {eid} references missing node {nid}")

    return BDFValidationResult(
        parse_success=True,
        missing_property_count=missing_properties,
        missing_material_count=missing_materials,
        duplicate_id_count=len(model.duplicate_ids),
        missing_nodes_count=missing_nodes,
        element_count=len(model.elements),
        shell_element_count=sum(1 for e in model.elements.values() if str(e["type"]) in shell_types),
        solid_element_count=sum(1 for e in model.elements.values() if str(e["type"]) in solid_types),
        connector_count=sum(1 for e in model.elements.values() if str(e["type"]) in connector_types),
        messages=messages + [f"duplicate {kind} id {value}" for kind, value in model.duplicate_ids],
    )


def validate_bdf(path: Path | str) -> BDFValidationResult:
    duplicate_ids = []
    try:
        text = Path(path).read_text(encoding="utf-8")
        duplicate_ids = _duplicate_ids(text.splitlines())
        return validate_model(read_bdf(path))
    except Exception as exc:
        return BDFValidationResult(
            parse_success=False,
            missing_property_count=0,
            missing_material_count=0,
            duplicate_id_count=len(duplicate_ids),
            missing_nodes_count=0,
            element_count=0,
            shell_element_count=0,
            solid_element_count=0,
            connector_count=0,
            messages=[str(exc), *[f"duplicate {kind} id {value}" for kind, value in duplicate_ids]],
        )
