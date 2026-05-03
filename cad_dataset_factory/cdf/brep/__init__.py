"""B-rep graph extraction utilities for CDF."""

from cad_dataset_factory.cdf.brep.feature_detector import (
    DetectedFeatureCandidate,
    FeatureCandidateDetectionError,
    attach_feature_candidates,
    detect_feature_candidates,
    extract_brep_graph_with_candidates,
)
from cad_dataset_factory.cdf.brep.graph_extractor import (
    BrepGraph,
    BrepGraphBuildError,
    extract_brep_graph,
    validate_brep_graph_structure,
    write_brep_graph,
    write_graph_schema,
)

__all__ = [
    "BrepGraph",
    "BrepGraphBuildError",
    "DetectedFeatureCandidate",
    "FeatureCandidateDetectionError",
    "attach_feature_candidates",
    "detect_feature_candidates",
    "extract_brep_graph",
    "extract_brep_graph_with_candidates",
    "validate_brep_graph_structure",
    "write_brep_graph",
    "write_graph_schema",
]
