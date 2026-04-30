from __future__ import annotations

from .sheet_metal_box import SheetMetalBoxTemplate


class PcbDummyTemplate(SheetMetalBoxTemplate):
    name = "pcb_dummy"
    strategy = "mass_only"
    material_id = "MAT_PCB"
