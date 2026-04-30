from __future__ import annotations

from .sheet_metal_box import SheetMetalBoxTemplate


class ScrewTemplate(SheetMetalBoxTemplate):
    name = "screw"
    strategy = "solid"
    material_id = "MAT_STEEL"
