"""Sampling utilities for CDF."""

from cad_dataset_factory.cdf.sampling.feature_layout import (
    BendKeepout,
    FeatureLayoutReport,
    FeaturePlacementCandidate,
    FeaturePlacementError,
    PatchRegion,
    PlacementPolicy,
    sample_feature_layout,
    to_flat_panel_feature_specs,
    validate_feature_layout,
)

__all__ = [
    "BendKeepout",
    "FeatureLayoutReport",
    "FeaturePlacementCandidate",
    "FeaturePlacementError",
    "PatchRegion",
    "PlacementPolicy",
    "sample_feature_layout",
    "to_flat_panel_feature_specs",
    "validate_feature_layout",
]
