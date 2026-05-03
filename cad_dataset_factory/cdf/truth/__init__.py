"""Truth metadata and matching utilities for CDF."""

from cad_dataset_factory.cdf.truth.matching import (
    FeatureMatchingError,
    build_feature_matching_report,
    match_feature_truth_to_candidates,
    write_feature_matching_report,
)

__all__ = [
    "FeatureMatchingError",
    "build_feature_matching_report",
    "match_feature_truth_to_candidates",
    "write_feature_matching_report",
]
