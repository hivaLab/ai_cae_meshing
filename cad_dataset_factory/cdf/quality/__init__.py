"""CDF entity-quality utilities.

Primary quality evidence now lives in CDF entity-quality labels.
"""

from cad_dataset_factory.cdf.quality.entity_size_sweep import (
    EntitySizeSweepError,
    EntitySizeSweepResult,
    SizeSweepVariant,
    build_size_sweep_variants,
    run_entity_size_sweep,
    write_size_sweep_variants,
)

__all__ = [
    "EntitySizeSweepError",
    "EntitySizeSweepResult",
    "SizeSweepVariant",
    "build_size_sweep_variants",
    "run_entity_size_sweep",
    "write_size_sweep_variants",
]
