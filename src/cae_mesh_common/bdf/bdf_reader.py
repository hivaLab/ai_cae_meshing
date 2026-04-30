from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BDFModel:
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    elements: dict[int, dict[str, object]] = field(default_factory=dict)
    properties: dict[int, dict[str, object]] = field(default_factory=dict)
    materials: dict[int, dict[str, object]] = field(default_factory=dict)
    duplicate_ids: list[tuple[str, int]] = field(default_factory=list)
    raw_cards: list[list[str]] = field(default_factory=list)


def _split_card(line: str) -> list[str]:
    clean = line.split("$", 1)[0].strip()
    if not clean:
        return []
    if "," in clean:
        return [part.strip() for part in clean.split(",")]
    return clean.split()


def _add_unique(bucket: dict[int, object], key: int, value: object, model: BDFModel, kind: str) -> None:
    if key in bucket:
        model.duplicate_ids.append((kind, key))
    bucket[key] = value


def read_bdf(path: Path | str) -> BDFModel:
    model = BDFModel()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        card = _split_card(line)
        if not card:
            continue
        model.raw_cards.append(card)
        name = card[0].upper()
        try:
            if name == "GRID":
                nid = int(card[1])
                coords = (float(card[3]), float(card[4]), float(card[5]))
                _add_unique(model.nodes, nid, coords, model, "GRID")
            elif name in {"CQUAD4", "CTRIA3", "CTETRA", "CTETRA10", "CBUSH", "RBE2", "RBE3", "CONM2"}:
                eid = int(card[1])
                pid = int(card[2]) if name not in {"RBE2", "RBE3", "CONM2"} and len(card) > 2 and card[2] else None
                node_start = 3 if pid is not None else 2
                nodes = [int(value) for value in card[node_start:] if value and value.lstrip("-").isdigit()]
                _add_unique(model.elements, eid, {"type": name, "pid": pid, "nodes": nodes}, model, name)
            elif name == "PSHELL":
                pid = int(card[1])
                mid = int(card[2])
                thickness = float(card[3]) if len(card) > 3 and card[3] else 1.0
                _add_unique(model.properties, pid, {"type": name, "mid": mid, "thickness": thickness}, model, name)
            elif name in {"PSOLID", "PBUSH"}:
                pid = int(card[1])
                mid = int(card[2]) if len(card) > 2 and card[2] else 0
                _add_unique(model.properties, pid, {"type": name, "mid": mid}, model, name)
            elif name == "MAT1":
                mid = int(card[1])
                young = float(card[2]) if len(card) > 2 and card[2] else 1.0
                _add_unique(model.materials, mid, {"type": name, "young_modulus": young}, model, name)
        except (IndexError, ValueError) as exc:
            model.duplicate_ids.append((f"PARSE_ERROR:{name}", len(model.raw_cards)))
    return model
