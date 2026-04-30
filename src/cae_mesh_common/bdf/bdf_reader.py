from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass
class BDFModel:
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    elements: dict[int, dict[str, object]] = field(default_factory=dict)
    properties: dict[int, dict[str, object]] = field(default_factory=dict)
    materials: dict[int, dict[str, object]] = field(default_factory=dict)
    duplicate_ids: list[tuple[str, int]] = field(default_factory=list)
    raw_cards: list[list[str]] = field(default_factory=list)
    parser: str = "pyNastran"


def _split_card(line: str) -> list[str]:
    clean = line.split("$", 1)[0].strip()
    if not clean:
        return []
    if "," in clean:
        return [part.strip() for part in clean.split(",")]
    return clean.split()


_NASTRAN_FLOAT_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$")


def _parse_float(value: str) -> float:
    normalized = value.strip().replace("D", "E").replace("d", "E")
    try:
        return float(normalized)
    except ValueError:
        match = _NASTRAN_FLOAT_RE.match(normalized)
        if match:
            return float(f"{match.group(1)}E{match.group(2)}")
        raise


def _add_unique(bucket: dict[int, object], key: int, value: object, model: BDFModel, kind: str) -> None:
    if key in bucket:
        model.duplicate_ids.append((kind, key))
    bucket[key] = value


def read_bdf_lines(lines: list[str]) -> BDFModel:
    model = _read_with_pynastran(lines)
    model.duplicate_ids.extend(_duplicate_ids(lines))
    return model


def read_bdf_text(text: str) -> BDFModel:
    return read_bdf_lines(text.splitlines())


def read_bdf(path: Path | str) -> BDFModel:
    return read_bdf_text(Path(path).read_text(encoding="utf-8"))


def _read_with_pynastran(lines: list[str]) -> BDFModel:
    try:
        from pyNastran.bdf.bdf import BDF
    except ImportError as exc:
        raise RuntimeError("pyNastran is required for strict BDF validation") from exc

    text = _as_full_deck(lines)
    with NamedTemporaryFile("w", suffix=".bdf", delete=False, encoding="utf-8") as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    try:
        nastran = BDF(debug=False, log=None)
        nastran.read_bdf(temp_path, validate=True, xref=False, punch=False, read_includes=False)
        return _from_pynastran_model(nastran)
    finally:
        temp_path.unlink(missing_ok=True)


def _as_full_deck(lines: list[str]) -> str:
    nonempty = [line for line in lines if line.strip()]
    has_cend = any(line.strip().upper().startswith("CEND") for line in nonempty)
    has_begin_bulk = any(line.strip().upper().startswith("BEGIN BULK") for line in nonempty)
    if has_cend:
        prepared = nonempty
    elif has_begin_bulk:
        prepared = ["SOL 101", "CEND", *nonempty]
    else:
        prepared = ["SOL 101", "CEND", "BEGIN BULK", *nonempty, "ENDDATA"]
    return "\n".join(prepared) + "\n"


def _from_pynastran_model(nastran: object) -> BDFModel:
    model = BDFModel()
    for nid, node in nastran.nodes.items():
        xyz = [float(value) for value in node.xyz]
        model.nodes[int(nid)] = (xyz[0], xyz[1], xyz[2])
    for eid, element in nastran.elements.items():
        _add_pynastran_element(model, eid, element)
    for eid, element in getattr(nastran, "masses", {}).items():
        _add_pynastran_element(model, eid, element)
    for eid, element in getattr(nastran, "rigid_elements", {}).items():
        _add_pynastran_element(model, eid, element)
    for pid, prop in nastran.properties.items():
        ptype = str(prop.type).upper()
        mid = _property_material_id(prop)
        model.properties[int(pid)] = {"type": ptype, "mid": mid}
    for mid, material in nastran.materials.items():
        model.materials[int(mid)] = {
            "type": str(material.type).upper(),
            "young_modulus": float(getattr(material, "e", 0.0) or 0.0),
        }
    return model


def _add_pynastran_element(model: BDFModel, eid: int, element: object) -> None:
    etype = str(element.type).upper()
    pid = getattr(element, "pid", None)
    pid_value = None if etype in {"CONM2", "RBE2", "RBE3"} or pid in {None, 0} else int(pid)
    model.elements[int(eid)] = {"type": etype, "pid": pid_value, "nodes": _node_ids(element)}


def _node_ids(element: object) -> list[int]:
    for attr in ("node_ids", "nodes"):
        values = getattr(element, attr, None)
        if values is not None:
            return [int(node_id) for node_id in values if node_id is not None and isinstance(node_id, (int, float))]
    for attr in ("nid", "node_id", "ga", "gb"):
        value = getattr(element, attr, None)
        if value is not None:
            return [int(value)]
    return []


def _property_material_id(prop: object) -> int:
    for attr in ("mid1", "mid", "mid_ref"):
        value = getattr(prop, attr, None)
        if isinstance(value, int):
            return int(value)
        if hasattr(value, "mid"):
            return int(value.mid)
    return 0


def _duplicate_ids(lines: list[str]) -> list[tuple[str, int]]:
    model = BDFModel(parser="lightweight_duplicate_scan")
    for line in lines:
        card = _split_card(line)
        if not card:
            continue
        model.raw_cards.append(card)
        name = card[0].upper()
        try:
            if name == "GRID":
                nid = int(card[1])
                coords = (_parse_float(card[3]), _parse_float(card[4]), _parse_float(card[5]))
                _add_unique(model.nodes, nid, coords, model, "GRID")
            elif name in {
                "CQUAD4",
                "CTRIA3",
                "CTETRA",
                "CTETRA10",
                "CHEXA",
                "CPENTA",
                "CPYRA",
                "CBUSH",
                "RBE2",
                "RBE3",
                "CONM2",
            }:
                eid = int(card[1])
                pid = int(card[2]) if name not in {"RBE2", "RBE3", "CONM2"} and len(card) > 2 and card[2] else None
                node_start = 3 if pid is not None else 2
                nodes = [int(value) for value in card[node_start:] if value and value.lstrip("-").isdigit()]
                _add_unique(model.elements, eid, {"type": name, "pid": pid, "nodes": nodes}, model, name)
            elif name == "PSHELL":
                pid = int(card[1])
                mid = int(card[2])
                thickness = _parse_float(card[3]) if len(card) > 3 and card[3] else 1.0
                _add_unique(model.properties, pid, {"type": name, "mid": mid, "thickness": thickness}, model, name)
            elif name == "PSOLID":
                pid = int(card[1])
                mid = int(card[2]) if len(card) > 2 and card[2] else 0
                _add_unique(model.properties, pid, {"type": name, "mid": mid}, model, name)
            elif name == "PBUSH":
                pid = int(card[1])
                mid = int(card[2]) if len(card) > 2 and card[2].lstrip("-").isdigit() else 0
                _add_unique(model.properties, pid, {"type": name, "mid": mid}, model, name)
            elif name == "MAT1":
                mid = int(card[1])
                young = _parse_float(card[2]) if len(card) > 2 and card[2] else 1.0
                _add_unique(model.materials, mid, {"type": name, "young_modulus": young}, model, name)
        except (IndexError, ValueError) as exc:
            model.duplicate_ids.append((f"PARSE_ERROR:{name}", len(model.raw_cards)))
    return model.duplicate_ids
