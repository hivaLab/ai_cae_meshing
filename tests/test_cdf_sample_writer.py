from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.dataset import (
    SampleWriteError,
    build_sample_acceptance,
    write_dataset_index,
    write_sample_directory,
)
from cad_dataset_factory.cdf.labels import build_aux_labels
from test_cdf_manifest_writer import build_valid_manifest, entity_signatures, feature_truth, mesh_policy

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ID = "sample_000001"


def _accepted_by(**overrides: bool) -> dict[str, bool]:
    values = {
        "geometry_validation": True,
        "feature_matching": True,
        "manifest_schema": True,
        "ansa_oracle": True,
    }
    values.update(overrides)
    return values


def _sample_docs() -> tuple[dict, dict]:
    manifest = build_valid_manifest()
    aux_labels = build_aux_labels(SAMPLE_ID, manifest, mesh_policy())
    return manifest, aux_labels


def test_build_sample_acceptance_preserves_booleans() -> None:
    acceptance = build_sample_acceptance(SAMPLE_ID, _accepted_by(ansa_oracle=False), "ansa_oracle_failed")

    assert acceptance == {
        "schema": "CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1",
        "sample_id": SAMPLE_ID,
        "accepted": False,
        "accepted_by": _accepted_by(ansa_oracle=False),
        "rejection_reason": "ansa_oracle_failed",
    }


def test_write_sample_directory_creates_core_dataset_structure() -> None:
    manifest, aux_labels = _sample_docs()
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_sample_writer" / "samples" / SAMPLE_ID
    acceptance = build_sample_acceptance(SAMPLE_ID, _accepted_by())

    write_sample_directory(
        sample_root,
        feature_truth=feature_truth(),
        entity_signatures=entity_signatures(),
        manifest=manifest,
        aux_labels=aux_labels,
        acceptance=acceptance,
        generator_params={
            "schema": "CDF_GENERATOR_PARAMS_SM_V1",
            "sample_id": SAMPLE_ID,
            "part_class": "SM_FLAT_PANEL",
        },
    )

    for dirname in ("cad", "metadata", "graph", "labels", "meshes", "reports"):
        assert (sample_root / dirname).is_dir()

    expected_files = [
        "metadata/generator_params.json",
        "metadata/feature_truth.json",
        "metadata/entity_signatures.json",
        "labels/amg_manifest.json",
        "labels/face_labels.json",
        "labels/edge_labels.json",
        "labels/feature_labels.json",
        "reports/sample_acceptance.json",
    ]
    for filename in expected_files:
        assert (sample_root / filename).is_file()

    loaded_acceptance = json.loads((sample_root / "reports" / "sample_acceptance.json").read_text(encoding="utf-8"))
    assert loaded_acceptance["accepted_by"] == _accepted_by()
    assert loaded_acceptance["accepted"] is True


def test_write_dataset_index_uses_stable_relative_paths() -> None:
    dataset_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_sample_writer" / "dataset_index"

    index = write_dataset_index(
        dataset_root,
        accepted_samples=[SAMPLE_ID],
        rejected_samples=[
            {
                "sample_attempt_id": "attempt_000002",
                "reason": "FEATURE_CLEARANCE",
                "phase": "sampling",
            }
        ],
        config_used={"schema": "CDF_CONFIG_SM_ANSA_V1", "seed": 1234},
    )

    written = json.loads((dataset_root / "dataset_index.json").read_text(encoding="utf-8"))
    assert written == index
    assert written["schema"] == "CDF_DATASET_INDEX_SM_V1"
    assert written["accepted_samples"] == [
        {
            "sample_id": SAMPLE_ID,
            "sample_dir": f"samples/{SAMPLE_ID}",
            "manifest": f"samples/{SAMPLE_ID}/labels/amg_manifest.json",
            "acceptance_report": f"samples/{SAMPLE_ID}/reports/sample_acceptance.json",
        }
    ]
    assert (dataset_root / "config_used.json").is_file()


def test_malformed_acceptance_raises_sample_write_error() -> None:
    manifest, aux_labels = _sample_docs()
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_sample_writer" / "samples" / SAMPLE_ID
    malformed_acceptance = {
        "schema": "CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1",
        "sample_id": SAMPLE_ID,
        "accepted": True,
        "accepted_by": {"geometry_validation": True},
        "rejection_reason": None,
    }

    with pytest.raises(SampleWriteError) as exc_info:
        write_sample_directory(
            sample_root,
            feature_truth=feature_truth(),
            entity_signatures=entity_signatures(),
            manifest=manifest,
            aux_labels=aux_labels,
            acceptance=malformed_acceptance,
        )
    assert exc_info.value.code == "malformed_accepted_by"
    assert exc_info.value.sample_id == SAMPLE_ID


def test_sample_id_mismatch_raises_sample_write_error() -> None:
    manifest, aux_labels = _sample_docs()
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_sample_writer" / "samples" / "sample_999999"

    with pytest.raises(SampleWriteError) as exc_info:
        write_sample_directory(
            sample_root,
            feature_truth=feature_truth(),
            entity_signatures=entity_signatures(),
            manifest=manifest,
            aux_labels=aux_labels,
            acceptance=build_sample_acceptance(SAMPLE_ID, _accepted_by()),
        )
    assert exc_info.value.code == "sample_id_mismatch"
    assert exc_info.value.sample_id == SAMPLE_ID
