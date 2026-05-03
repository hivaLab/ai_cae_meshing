"""AMG-compatible deterministic label rules owned by CDF."""

from cad_dataset_factory.cdf.labels.amg_rules import (
    bend_rule,
    cutout_rule,
    flange_rule,
    hole_rule,
    slot_rule,
)
from cad_dataset_factory.cdf.labels.manifest_writer import (
    FeatureClearance,
    ManifestBuildError,
    build_amg_manifest,
    write_amg_manifest,
)

__all__ = [
    "FeatureClearance",
    "ManifestBuildError",
    "bend_rule",
    "build_amg_manifest",
    "cutout_rule",
    "flange_rule",
    "hole_rule",
    "slot_rule",
    "write_amg_manifest",
]
