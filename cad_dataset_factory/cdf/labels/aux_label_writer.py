"""Build auxiliary training labels from schema-valid AMG manifests."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from cad_dataset_factory.cdf.domain import MeshPolicy

FEATURE_LABEL_SCHEMA = "CDF_FEATURE_LABELS_SM_V1"
EDGE_LABEL_SCHEMA = "CDF_EDGE_LABELS_SM_V1"
FACE_LABEL_SCHEMA = "CDF_FACE_LABELS_SM_V1"

_TARGET_LENGTH_KEYS = (
    "edge_target_length_mm",
    "bend_target_length_mm",
    "flange_target_length_mm",
    "free_edge_target_length_mm",
)
_DIVISION_KEYS = (
    "circumferential_divisions",
    "end_arc_divisions",
    "slot_end_divisions",
    "straight_edge_divisions",
    "bend_rows",
    "min_elements_across_width",
)


class AuxLabelBuildError(ValueError):
    """Raised when manifest-derived auxiliary labels cannot be built safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool) and not (
        isinstance(value, float) and not math.isfinite(value)
    )


def _normalize_json_mapping(value: Mapping[str, Any], *, feature_id: str | None = None) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AuxLabelBuildError(
            "non_json_compatible_value",
            "label inputs must be JSON-compatible",
            feature_id,
        ) from exc


def _require_features(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "AMG_MANIFEST_SM_V1":
        raise AuxLabelBuildError("invalid_manifest_schema", "manifest schema_version must be AMG_MANIFEST_SM_V1")
    if manifest.get("status") != "VALID":
        raise AuxLabelBuildError("invalid_manifest_status", "auxiliary labels require a VALID manifest")

    raw_features = manifest.get("features")
    if not isinstance(raw_features, list):
        raise AuxLabelBuildError("malformed_manifest_features", "manifest features must be a list")

    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_feature in raw_features:
        if not isinstance(raw_feature, dict):
            raise AuxLabelBuildError("malformed_manifest_feature", "manifest feature records must be objects")

        feature_id = raw_feature.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id:
            raise AuxLabelBuildError("missing_feature_id", "manifest feature records require non-empty feature_id")
        if feature_id in seen:
            raise AuxLabelBuildError("duplicate_feature_id", "manifest feature ids must be unique", feature_id)
        seen.add(feature_id)

        for key in ("type", "role", "action"):
            if not isinstance(raw_feature.get(key), str) or not raw_feature[key]:
                raise AuxLabelBuildError("malformed_manifest_feature", f"manifest feature requires string {key}", feature_id)

        controls = raw_feature.get("controls")
        if not isinstance(controls, dict) or not controls:
            raise AuxLabelBuildError("malformed_controls", "manifest feature controls must be a non-empty object", feature_id)
        _normalize_json_mapping(controls, feature_id=feature_id)
        features.append(raw_feature)

    return features


def _flatten_controls(controls: Mapping[str, Any], feature_id: str) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in controls.items():
        if not _is_json_scalar(value):
            raise AuxLabelBuildError(
                "non_scalar_control",
                "feature_labels can only flatten JSON scalar control values",
                feature_id,
            )
        flattened[key] = value
    return flattened


def _first_control_value(controls: Mapping[str, Any], keys: Sequence[str], feature_id: str) -> Any:
    for key in keys:
        if key in controls and controls[key] is not None:
            value = controls[key]
            if not _is_json_scalar(value):
                raise AuxLabelBuildError("non_scalar_control", f"control {key} must be a JSON scalar", feature_id)
            return value
    return None


def build_feature_labels(sample_id: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten manifest feature records into CDF feature training labels."""

    features = _require_features(manifest)
    labels: list[dict[str, Any]] = []

    for feature in features:
        feature_id = feature["feature_id"]
        label = {
            "feature_id": feature_id,
            "type": feature["type"],
            "role": feature["role"],
            "action": feature["action"],
        }
        label.update(_flatten_controls(feature["controls"], feature_id))
        labels.append(label)

    if {label["feature_id"] for label in labels} != {feature["feature_id"] for feature in features}:
        raise AuxLabelBuildError("feature_label_id_mismatch", "feature labels must match manifest feature ids 1:1")

    return {
        "schema": FEATURE_LABEL_SCHEMA,
        "sample_id": sample_id,
        "labels": labels,
    }


def build_edge_labels(sample_id: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Create deterministic boundary edge labels from manifest feature controls."""

    features = _require_features(manifest)
    manifest_feature_ids = {feature["feature_id"] for feature in features}
    labels: list[dict[str, Any]] = []

    for feature in features:
        feature_id = feature["feature_id"]
        controls = feature["controls"]
        is_suppressed = feature["action"] == "SUPPRESS"
        label: dict[str, Any] = {
            "edge_signature_id": f"EDGE_SIG_{feature_id}_BOUNDARY",
            "feature_id": feature_id,
            "preserve_edge": not is_suppressed,
            "boundary_capture": not is_suppressed,
        }

        target_length = _first_control_value(controls, _TARGET_LENGTH_KEYS, feature_id)
        if target_length is not None:
            label["target_length_mm"] = target_length

        divisions = _first_control_value(controls, _DIVISION_KEYS, feature_id)
        if divisions is not None:
            label["number_of_divisions"] = divisions

        labels.append(label)

    if not {label["feature_id"] for label in labels}.issubset(manifest_feature_ids):
        raise AuxLabelBuildError("edge_label_id_mismatch", "edge labels must reference manifest feature ids")

    return {
        "schema": EDGE_LABEL_SCHEMA,
        "sample_id": sample_id,
        "labels": labels,
    }


def build_face_labels(
    sample_id: str,
    mesh_policy: MeshPolicy | Mapping[str, Any],
    face_label_inputs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize optional face labels; default to empty labels until face signatures exist."""

    if isinstance(mesh_policy, MeshPolicy):
        mesh_policy.model_dump(mode="json")
    else:
        _normalize_json_mapping(mesh_policy)

    labels: list[dict[str, Any]] = []
    for raw_label in face_label_inputs or ():
        if not isinstance(raw_label, Mapping):
            raise AuxLabelBuildError("malformed_face_label", "face label inputs must be objects")
        labels.append(_normalize_json_mapping(raw_label))

    return {
        "schema": FACE_LABEL_SCHEMA,
        "sample_id": sample_id,
        "labels": labels,
    }


def build_aux_labels(
    sample_id: str,
    manifest: Mapping[str, Any],
    mesh_policy: MeshPolicy | Mapping[str, Any],
    face_label_inputs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build all auxiliary label documents for one sample."""

    return {
        "face_labels": build_face_labels(sample_id, mesh_policy, face_label_inputs),
        "edge_labels": build_edge_labels(sample_id, manifest),
        "feature_labels": build_feature_labels(sample_id, manifest),
    }


def write_aux_labels(labels_dir: str | Path, aux_labels: Mapping[str, Mapping[str, Any]]) -> None:
    """Write feature, edge, and face auxiliary labels below a labels directory."""

    output_dir = Path(labels_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filenames = {
        "face_labels": "face_labels.json",
        "edge_labels": "edge_labels.json",
        "feature_labels": "feature_labels.json",
    }
    for key, filename in filenames.items():
        if key not in aux_labels:
            raise AuxLabelBuildError("missing_aux_label_document", f"missing {key} document")
        normalized = _normalize_json_mapping(aux_labels[key])
        (output_dir / filename).write_text(
            json.dumps(normalized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
