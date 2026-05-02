from __future__ import annotations

from typing import Any

from cae_dataset_factory.labeling.edge_semantic_oracle import edge_labels
from cae_dataset_factory.labeling.size_field_oracle import size_for_part

TARGET_TYPES = {"part", "face", "edge", "feature", "contact_candidate", "connection"}


def mesh_size_labels(assembly: dict[str, Any]) -> list[dict[str, Any]]:
    """Create feature-aware refinement labels that can map directly to AMG recipe zones."""

    defects_by_part: dict[str, int] = {}
    for defect in assembly.get("defects", []):
        defects_by_part[defect["part_uid"]] = defects_by_part.get(defect["part_uid"], 0) + 1

    part_base = {
        part["part_uid"]: size_for_part(part, defects_by_part.get(part["part_uid"], 0))
        for part in assembly.get("parts", [])
    }
    named_boundary_parts = _named_boundary_parts(assembly)
    labels: list[dict[str, Any]] = []

    for part in assembly.get("parts", []):
        part_uid = part["part_uid"]
        base_size = part_base[part_uid]
        labels.append(
            _label(
                target_uid=part_uid,
                target_type="part",
                source_feature_type="part_baseline",
                base_size=base_size,
                factor=1.0,
                reason="part_baseline",
                required=True,
                confidence_source="synthetic_oracle",
            )
        )

        features_by_face: dict[str, list[dict[str, Any]]] = {}
        for feature in part.get("features", []):
            features_by_face.setdefault(feature["face_uid"], []).append(feature)
            labels.append(
                _label(
                    target_uid=feature["feature_uid"],
                    target_type="feature",
                    source_feature_type=str(feature.get("feature_type", "unknown_feature")),
                    base_size=base_size,
                    factor=_feature_factor(str(feature.get("feature_type", ""))),
                    reason=_feature_reason(str(feature.get("feature_type", ""))),
                    required=bool(feature.get("preserve", False)),
                    confidence_source="synthetic_oracle_feature",
                )
            )

        for face in part.get("face_signatures", []):
            face_uid = face["face_uid"]
            face_features = features_by_face.get(face_uid, [])
            if face_features:
                primary = str(face_features[0].get("feature_type", "feature"))
                factor = min(_feature_factor(str(item.get("feature_type", ""))) for item in face_features)
                reason = _feature_reason(primary)
                required = any(bool(item.get("preserve", False)) for item in face_features)
                source = primary
            elif part_uid in named_boundary_parts:
                factor = 0.65
                reason = "named_boundary_refinement"
                required = True
                source = "named_boundary"
            elif _is_thin_region(part):
                factor = 0.72
                reason = "thin_region_refinement"
                required = True
                source = "thin_region"
            else:
                factor = 0.95
                reason = "face_baseline"
                required = False
                source = "face"
            labels.append(
                _label(
                    target_uid=face_uid,
                    target_type="face",
                    source_feature_type=source,
                    base_size=base_size,
                    factor=factor,
                    reason=reason,
                    required=required,
                    confidence_source="synthetic_oracle_face",
                )
            )

        for edge in edge_labels(part):
            semantic = str(edge.get("semantic", "boundary_edge"))
            short_edge = "_z_" in edge["edge_uid"] and float(part["dimensions"]["height"]) < 8.0
            if semantic == "feature_edge":
                factor = 0.5
                reason = "feature_edge_refinement"
                source = "feature_edge"
                required = True
            elif short_edge:
                factor = 0.45
                reason = "short_edge_refinement"
                source = "short_edge"
                required = True
            elif _is_thin_region(part):
                factor = 0.7
                reason = "thin_edge_refinement"
                source = "thin_region"
                required = True
            else:
                factor = 0.9
                reason = "edge_baseline"
                source = semantic
                required = False
            labels.append(
                _label(
                    target_uid=edge["edge_uid"],
                    target_type="edge",
                    source_feature_type=source,
                    base_size=base_size,
                    factor=factor,
                    reason=reason,
                    required=required,
                    confidence_source="synthetic_oracle_edge",
                )
            )

    for connection in assembly.get("connections", []):
        a = connection["part_uid_a"]
        b = connection["part_uid_b"]
        base_size = min(part_base.get(a, 6.0), part_base.get(b, 6.0))
        diameter = float(connection.get("diameter_mm", 3.0))
        factor = 0.45 if bool(connection.get("preserve_hole", False)) else 0.65
        size = max(0.65, min(base_size * factor, max(0.8, diameter * 0.8)))
        labels.append(
            _explicit_label(
                target_uid=f"contact_{connection['connection_uid']}",
                target_type="contact_candidate",
                source_feature_type=str(connection.get("type", "contact")),
                size=size,
                reason="contact_or_connection_refinement",
                required=True,
                confidence_source="synthetic_oracle_connection",
            )
        )
        labels.append(
            _explicit_label(
                target_uid=connection["connection_uid"],
                target_type="connection",
                source_feature_type=str(connection.get("type", "connection")),
                size=size,
                reason="connection_mesh_control",
                required=True,
                confidence_source="synthetic_oracle_connection",
            )
        )

    _validate_labels(labels)
    return labels


def legacy_part_size_labels(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "part_uid": item["target_uid"],
            "target_size": item["target_size_mm"],
            "confidence": 1.0,
            "deprecated": True,
            "source": "mesh_size_labels.part",
        }
        for item in labels
        if item["target_type"] == "part"
    ]


def refinement_class(reason: str, source_feature_type: str = "") -> str:
    text = f"{reason} {source_feature_type}".lower()
    if "hole" in text or "screw" in text:
        return "hole"
    if "thin" in text:
        return "thin_region"
    if "rib" in text:
        return "rib_root"
    if "boss" in text:
        return "boss"
    if "contact" in text or "connection" in text:
        return "contact"
    if "boundary" in text:
        return "boundary"
    if "curv" in text or "cylind" in text:
        return "curvature"
    if "short" in text:
        return "short_edge"
    return "none"


def _label(
    *,
    target_uid: str,
    target_type: str,
    source_feature_type: str,
    base_size: float,
    factor: float,
    reason: str,
    required: bool,
    confidence_source: str,
) -> dict[str, Any]:
    size = max(0.5, float(base_size) * float(factor))
    return _explicit_label(
        target_uid=target_uid,
        target_type=target_type,
        source_feature_type=source_feature_type,
        size=size,
        reason=reason,
        required=required,
        confidence_source=confidence_source,
    )


def _explicit_label(
    *,
    target_uid: str,
    target_type: str,
    source_feature_type: str,
    size: float,
    reason: str,
    required: bool,
    confidence_source: str,
) -> dict[str, Any]:
    size = round(float(size), 4)
    return {
        "target_uid": str(target_uid),
        "target_type": str(target_type),
        "source_feature_type": str(source_feature_type),
        "target_size_mm": size,
        "min_size_mm": round(max(0.25, size * 0.55), 4),
        "max_size_mm": round(max(size, size * 1.75), 4),
        "refinement_reason": str(reason),
        "refinement_class": refinement_class(str(reason), str(source_feature_type)),
        "required": bool(required),
        "confidence_source": str(confidence_source),
    }


def _feature_factor(feature_type: str) -> float:
    feature_type = feature_type.lower()
    if "hole" in feature_type or "screw" in feature_type or "boss" in feature_type:
        return 0.42
    if "rib" in feature_type:
        return 0.48
    if "thin" in feature_type:
        return 0.55
    if "flange" in feature_type or "bend" in feature_type:
        return 0.62
    if "cylind" in feature_type or "shaft" in feature_type or "endcap" in feature_type:
        return 0.7
    return 0.75


def _feature_reason(feature_type: str) -> str:
    cls = refinement_class(feature_type, feature_type)
    return {
        "hole": "hole_or_boss_refinement",
        "thin_region": "thin_region_refinement",
        "rib_root": "rib_root_refinement",
        "boss": "boss_refinement",
        "curvature": "curvature_refinement",
    }.get(cls, "feature_refinement")


def _is_thin_region(part: dict[str, Any]) -> bool:
    thickness = float(part.get("nominal_thickness", 0.0) or 0.0)
    height = float(part.get("dimensions", {}).get("height", 0.0) or 0.0)
    return 0.0 < thickness <= 2.0 or 0.0 < height <= 3.0


def _named_boundary_parts(assembly: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for values in assembly.get("boundary_named_sets", {}).values():
        for value in values:
            result.add(str(value.get("part_uid") if isinstance(value, dict) else value))
    result.discard("")
    return result


def _validate_labels(labels: list[dict[str, Any]]) -> None:
    for item in labels:
        if item["target_type"] not in TARGET_TYPES:
            raise ValueError(f"invalid mesh size target_type {item['target_type']!r}")
        if item["min_size_mm"] > item["target_size_mm"]:
            raise ValueError(f"invalid mesh size min/target for {item['target_uid']}")
        if item["target_size_mm"] > item["max_size_mm"]:
            raise ValueError(f"invalid mesh size target/max for {item['target_uid']}")
