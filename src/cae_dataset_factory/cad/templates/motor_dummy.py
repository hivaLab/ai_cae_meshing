from __future__ import annotations

from .sheet_metal_box import SheetMetalBoxTemplate


class MotorDummyTemplate(SheetMetalBoxTemplate):
    name = "motor_dummy"
    strategy = "solid"
    material_id = "MAT_ALUMINUM"
