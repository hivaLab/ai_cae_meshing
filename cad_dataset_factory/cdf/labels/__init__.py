"""AMG-compatible deterministic label rules owned by CDF."""

from cad_dataset_factory.cdf.labels.amg_rules import (
    bend_rule,
    cutout_rule,
    flange_rule,
    hole_rule,
    slot_rule,
)
from cad_dataset_factory.cdf.labels.aux_label_writer import (
    AuxLabelBuildError,
    build_aux_labels,
    build_edge_labels,
    build_face_labels,
    build_feature_labels,
    write_aux_labels,
)
from cad_dataset_factory.cdf.labels.manifest_writer import (
    FeatureClearance,
    ManifestBuildError,
    build_amg_manifest,
    write_amg_manifest,
)

__all__ = [
    "AuxLabelBuildError",
    "FeatureClearance",
    "ManifestBuildError",
    "bend_rule",
    "build_amg_manifest",
    "build_aux_labels",
    "build_edge_labels",
    "build_face_labels",
    "build_feature_labels",
    "cutout_rule",
    "flange_rule",
    "hole_rule",
    "slot_rule",
    "write_aux_labels",
    "write_amg_manifest",
]
