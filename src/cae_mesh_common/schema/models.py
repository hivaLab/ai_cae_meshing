from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Material:
    material_id: str
    name: str
    young_modulus: float
    poisson_ratio: float
    density: float


@dataclass(frozen=True)
class PartAttribute:
    part_uid: str
    name: str
    material_id: str
    nominal_thickness: float
    representation_hint: str
    is_named_boundary: bool = False


@dataclass(frozen=True)
class MeshProfile:
    profile_id: str
    units: str
    target_solver: str
    shell: dict[str, float]
    solid: dict[str, float]
    quality: dict[str, float]


@dataclass(frozen=True)
class MeshRecipe:
    recipe_id: str
    sample_id: str
    backend: str
    part_strategies: list[dict[str, Any]]
    size_fields: list[dict[str, Any]]
    connections: list[dict[str, Any]]
    refinement_zones: list[dict[str, Any]] = field(default_factory=list)
    guard: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "sample_id": self.sample_id,
            "backend": self.backend,
            "part_strategies": self.part_strategies,
            "size_fields": self.size_fields,
            "refinement_zones": self.refinement_zones,
            "connections": self.connections,
            "guard": self.guard,
        }


@dataclass(frozen=True)
class QAMetrics:
    sample_id: str
    accepted: bool
    bdf_parse_success: bool
    missing_property_count: int
    missing_material_count: int
    duplicate_id_count: int
    shell_element_count: int = 0
    solid_element_count: int = 0
    connector_count: int = 0
    max_shell_aspect: float = 1.0
    max_shell_skew: float = 0.0
    min_solid_jacobian: float = 1.0
    failed_regions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "accepted": self.accepted,
            "bdf_parse_success": self.bdf_parse_success,
            "missing_property_count": self.missing_property_count,
            "missing_material_count": self.missing_material_count,
            "duplicate_id_count": self.duplicate_id_count,
            "shell_element_count": self.shell_element_count,
            "solid_element_count": self.solid_element_count,
            "connector_count": self.connector_count,
            "max_shell_aspect": self.max_shell_aspect,
            "max_shell_skew": self.max_shell_skew,
            "min_solid_jacobian": self.min_solid_jacobian,
            "failed_regions": self.failed_regions,
        }
