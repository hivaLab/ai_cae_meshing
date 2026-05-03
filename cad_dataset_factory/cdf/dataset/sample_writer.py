"""Write CDF sample directories and dataset indexes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from cad_dataset_factory.cdf.domain import CdfBaseModel
from cad_dataset_factory.cdf.labels import write_amg_manifest, write_aux_labels

SAMPLE_ACCEPTANCE_SCHEMA = "CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1"
DATASET_INDEX_SCHEMA = "CDF_DATASET_INDEX_SM_V1"
ACCEPTED_BY_KEYS = (
    "geometry_validation",
    "feature_matching",
    "manifest_schema",
    "ansa_oracle",
)


class SampleWriteError(ValueError):
    """Raised when a CDF sample cannot be written without ambiguity."""

    def __init__(self, code: str, message: str, sample_id: str | None = None) -> None:
        self.code = code
        self.sample_id = sample_id
        prefix = code if sample_id is None else f"{code} [{sample_id}]"
        super().__init__(f"{prefix}: {message}")


def _json_dict(value: CdfBaseModel | Mapping[str, Any], *, code: str, sample_id: str | None = None) -> dict[str, Any]:
    if isinstance(value, CdfBaseModel):
        raw = value.model_dump(mode="json", exclude_none=True)
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise SampleWriteError(code, "expected a JSON-compatible mapping", sample_id)

    try:
        return json.loads(json.dumps(raw, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise SampleWriteError(code, "document must be JSON-compatible", sample_id) from exc


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    normalized = _json_dict(document, code="non_json_compatible_document")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_sample_id(document: Mapping[str, Any], *, code: str, expected: str | None = None) -> str:
    sample_id = document.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        raise SampleWriteError(code, "document requires a non-empty sample_id", expected)
    if expected is not None and sample_id != expected:
        raise SampleWriteError("sample_id_mismatch", f"expected {expected}, got {sample_id}", expected)
    return sample_id


def _validate_accepted_by(accepted_by: Mapping[str, Any], sample_id: str) -> dict[str, bool]:
    keys = set(accepted_by)
    expected = set(ACCEPTED_BY_KEYS)
    if keys != expected:
        raise SampleWriteError(
            "malformed_accepted_by",
            f"accepted_by keys must be exactly {', '.join(ACCEPTED_BY_KEYS)}",
            sample_id,
        )
    normalized: dict[str, bool] = {}
    for key in ACCEPTED_BY_KEYS:
        value = accepted_by[key]
        if not isinstance(value, bool):
            raise SampleWriteError("malformed_accepted_by", "accepted_by values must be booleans", sample_id)
        normalized[key] = value
    return normalized


def build_sample_acceptance(
    sample_id: str,
    accepted_by: Mapping[str, bool],
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    """Build the CDF sample acceptance report."""

    if not isinstance(sample_id, str) or not sample_id:
        raise SampleWriteError("missing_sample_id", "sample_id must be a non-empty string")
    normalized = _validate_accepted_by(accepted_by, sample_id)
    accepted = all(normalized.values())
    if accepted and rejection_reason is not None:
        raise SampleWriteError("malformed_acceptance", "accepted samples cannot have rejection_reason", sample_id)
    if rejection_reason is not None and not isinstance(rejection_reason, str):
        raise SampleWriteError("malformed_acceptance", "rejection_reason must be a string or null", sample_id)
    return {
        "schema": SAMPLE_ACCEPTANCE_SCHEMA,
        "sample_id": sample_id,
        "accepted": accepted,
        "accepted_by": normalized,
        "rejection_reason": rejection_reason,
    }


def _validate_acceptance(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _json_dict(acceptance, code="malformed_acceptance")
    if normalized.get("schema") != SAMPLE_ACCEPTANCE_SCHEMA:
        raise SampleWriteError("malformed_acceptance", f"schema must be {SAMPLE_ACCEPTANCE_SCHEMA}")
    sample_id = _require_sample_id(normalized, code="malformed_acceptance")
    accepted_by = normalized.get("accepted_by")
    if not isinstance(accepted_by, Mapping):
        raise SampleWriteError("malformed_acceptance", "accepted_by must be an object", sample_id)
    accepted_by = _validate_accepted_by(accepted_by, sample_id)
    accepted = normalized.get("accepted")
    if not isinstance(accepted, bool):
        raise SampleWriteError("malformed_acceptance", "accepted must be a boolean", sample_id)
    if accepted != all(accepted_by.values()):
        raise SampleWriteError("malformed_acceptance", "accepted must equal all accepted_by booleans", sample_id)
    rejection_reason = normalized.get("rejection_reason")
    if accepted and rejection_reason is not None:
        raise SampleWriteError("malformed_acceptance", "accepted samples cannot have rejection_reason", sample_id)
    if rejection_reason is not None and not isinstance(rejection_reason, str):
        raise SampleWriteError("malformed_acceptance", "rejection_reason must be a string or null", sample_id)
    normalized["accepted_by"] = accepted_by
    return normalized


def _validate_aux_labels(aux_labels: Mapping[str, Mapping[str, Any]], sample_id: str) -> dict[str, Mapping[str, Any]]:
    required = {"face_labels", "edge_labels", "feature_labels"}
    if set(aux_labels) != required:
        raise SampleWriteError("malformed_aux_labels", "aux_labels must contain face, edge, and feature documents", sample_id)
    for document in aux_labels.values():
        _require_sample_id(_json_dict(document, code="malformed_aux_labels", sample_id=sample_id), code="malformed_aux_labels", expected=sample_id)
    return dict(aux_labels)


def write_sample_directory(
    sample_root: str | Path,
    *,
    feature_truth: CdfBaseModel | Mapping[str, Any],
    entity_signatures: CdfBaseModel | Mapping[str, Any],
    manifest: Mapping[str, Any],
    aux_labels: Mapping[str, Mapping[str, Any]],
    acceptance: Mapping[str, Any],
    generator_params: Mapping[str, Any] | None = None,
    reports: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Write one accepted-sample directory from already-built CDF documents."""

    sample_path = Path(sample_root)
    normalized_acceptance = _validate_acceptance(acceptance)
    sample_id = normalized_acceptance["sample_id"]
    if sample_path.name != sample_id:
        raise SampleWriteError("sample_id_mismatch", "sample directory name must equal sample_id", sample_id)

    feature_truth_doc = _json_dict(feature_truth, code="malformed_feature_truth", sample_id=sample_id)
    entity_signatures_doc = _json_dict(entity_signatures, code="malformed_entity_signatures", sample_id=sample_id)
    _require_sample_id(feature_truth_doc, code="malformed_feature_truth", expected=sample_id)
    _require_sample_id(entity_signatures_doc, code="malformed_entity_signatures", expected=sample_id)
    _validate_aux_labels(aux_labels, sample_id)

    for dirname in ("cad", "metadata", "graph", "labels", "meshes", "reports"):
        (sample_path / dirname).mkdir(parents=True, exist_ok=True)

    if generator_params is not None:
        _write_json(sample_path / "metadata" / "generator_params.json", generator_params)
    _write_json(sample_path / "metadata" / "feature_truth.json", feature_truth_doc)
    _write_json(sample_path / "metadata" / "entity_signatures.json", entity_signatures_doc)

    write_amg_manifest(sample_path / "labels" / "amg_manifest.json", dict(manifest))
    write_aux_labels(sample_path / "labels", aux_labels)

    for name, document in (reports or {}).items():
        if not isinstance(name, str) or not name:
            raise SampleWriteError("malformed_report_name", "report names must be non-empty strings", sample_id)
        filename = name if name.endswith(".json") else f"{name}.json"
        _write_json(sample_path / "reports" / filename, document)
    _write_json(sample_path / "reports" / "sample_acceptance.json", normalized_acceptance)

    return {
        "sample_id": sample_id,
        "sample_dir": sample_path.as_posix(),
        "manifest": (sample_path / "labels" / "amg_manifest.json").as_posix(),
        "acceptance_report": (sample_path / "reports" / "sample_acceptance.json").as_posix(),
    }


def _accepted_index_record(sample: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(sample, str):
        sample_id = sample
        record: dict[str, Any] = {"sample_id": sample_id}
    elif isinstance(sample, Mapping):
        record = _json_dict(sample, code="malformed_dataset_index_sample")
        sample_id = _require_sample_id(record, code="malformed_dataset_index_sample")
    else:
        raise SampleWriteError("malformed_dataset_index_sample", "accepted samples must be ids or mappings")
    record.setdefault("sample_dir", f"samples/{sample_id}")
    record.setdefault("manifest", f"samples/{sample_id}/labels/amg_manifest.json")
    record.setdefault("acceptance_report", f"samples/{sample_id}/reports/sample_acceptance.json")
    return record


def _rejected_index_record(sample: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(sample, str):
        return {"sample_attempt_id": sample}
    if isinstance(sample, Mapping):
        return _json_dict(sample, code="malformed_dataset_index_sample")
    raise SampleWriteError("malformed_dataset_index_sample", "rejected samples must be ids or mappings")


def write_dataset_index(
    dataset_root: str | Path,
    accepted_samples: Sequence[str | Mapping[str, Any]],
    rejected_samples: Sequence[str | Mapping[str, Any]],
    config_used: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write dataset_index.json and optional config_used.json with stable relative paths."""

    root = Path(dataset_root)
    for dirname in ("contracts", "rejected", "samples", "splits"):
        (root / dirname).mkdir(parents=True, exist_ok=True)

    accepted_records = [_accepted_index_record(sample) for sample in accepted_samples]
    rejected_records = [_rejected_index_record(sample) for sample in rejected_samples]
    index = {
        "schema": DATASET_INDEX_SCHEMA,
        "num_accepted": len(accepted_records),
        "num_rejected": len(rejected_records),
        "accepted_samples": accepted_records,
        "rejected_samples": rejected_records,
    }
    _write_json(root / "dataset_index.json", index)
    if config_used is not None:
        _write_json(root / "config_used.json", config_used)
    return index
