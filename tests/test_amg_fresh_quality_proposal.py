from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.dataset import load_amg_dataset_sample
from ai_mesh_generator.amg.recommendation.fresh import (
    FreshProposalConfig,
    generate_fresh_candidate_manifests,
    run_fresh_quality_proposal,
    score_fresh_candidates,
)
from ai_mesh_generator.amg.recommendation.quality import load_candidate_manifests, load_quality_ranker
from ai_mesh_generator.amg.training.quality import QualityTrainingConfig, run_quality_training
from test_amg_quality_recommendation import RUNS, ROOT, _fake_subprocess_run, _write_fixture

pytestmark = pytest.mark.model


def _canonical_hash(document: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _manifest_validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_fresh_candidates_are_schema_valid_deterministic_and_not_prior_perturbations() -> None:
    dataset, quality, training = _write_fixture("fresh_candidates")
    sample = load_amg_dataset_sample(dataset / "samples" / "sample_000001")
    prior_hashes = {_canonical_hash(candidate["manifest"]) for candidate in load_candidate_manifests(quality_exploration_root=quality, sample_id=sample.sample_id)}

    first = generate_fresh_candidate_manifests(sample, sample.manifest.manifest, candidates_per_sample=4, seed=710, disallowed_hashes=prior_hashes)
    second = generate_fresh_candidate_manifests(sample, sample.manifest.manifest, candidates_per_sample=4, seed=710, disallowed_hashes=prior_hashes)
    ranker = load_quality_ranker(training)
    scored = score_fresh_candidates(sample, first, ranker)

    assert [candidate.candidate_hash for candidate in first] == [candidate.candidate_hash for candidate in second]
    assert len({candidate.candidate_hash for candidate in first}) == 4
    assert not prior_hashes.intersection(candidate.candidate_hash for candidate in first)
    for candidate in first:
        assert not list(_manifest_validator().iter_errors(candidate.manifest))
        controls = candidate.manifest["features"][0]["controls"]
        mesh = candidate.manifest["global_mesh"]
        assert mesh["h_min_mm"] <= controls["edge_target_length_mm"] <= mesh["h_max_mm"]
        assert controls["circumferential_divisions"] >= 1
    assert all(candidate.predicted_score is not None for candidate in scored)


def test_fresh_candidates_expand_suppressed_cutout_into_refined_controls() -> None:
    dataset, _quality, _training = _write_fixture("fresh_suppressed")
    sample = load_amg_dataset_sample(dataset / "samples" / "sample_000001")
    suppressed = dict(sample.manifest.manifest)
    suppressed["features"] = [
        {
            "feature_id": "CUTOUT_RELIEF_0001",
            "type": "CUTOUT",
            "role": "RELIEF",
            "action": "SUPPRESS",
            "geometry_signature": {"geometry_signature": "CUTOUT:72.000:51.500:3.500:3.500"},
            "controls": {"suppression_rule": "small_relief_or_drain_area"},
        }
    ]

    generated = generate_fresh_candidate_manifests(
        sample,
        suppressed,
        candidates_per_sample=2,
        seed=710,
        disallowed_hashes={_canonical_hash(suppressed)},
    )

    assert len(generated) == 2
    assert all(candidate.manifest["features"][0]["action"] == "KEEP_REFINED" for candidate in generated)
    assert all("edge_target_length_mm" in candidate.manifest["features"][0]["controls"] for candidate in generated)


def test_fresh_proposal_writes_appendable_real_evidence_and_training_reads_it(monkeypatch) -> None:
    dataset, quality, training = _write_fixture("fresh_run")
    out = RUNS / "fresh_run" / "fresh_quality_exploration"
    ansa = RUNS / "fresh_run" / "ansa64.bat"
    ansa.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr("ai_mesh_generator.amg.recommendation.quality.subprocess.run", _fake_subprocess_run)

    result = run_fresh_quality_proposal(
        FreshProposalConfig(
            dataset_root=dataset,
            quality_exploration_root=quality,
            training_root=training,
            output_dir=out,
            ansa_executable=ansa,
            candidates_per_sample=2,
            seed=710,
        )
    )

    assert result.status == "SUCCESS"
    assert result.generated_count == 2
    summary = json.loads(Path(result.summary_path).read_text(encoding="utf-8"))
    assert summary["schema"] == "AMG_FRESH_QUALITY_EXPLORATION_SUMMARY_V1"
    assert summary["blocked_count"] == 0
    fresh_records = [record for record in summary["records"] if record.get("is_fresh_candidate")]
    assert len(fresh_records) == 2
    assert all(record["schema"] == "AMG_FRESH_QUALITY_EVIDENCE_V1" for record in fresh_records)
    assert all(isinstance(record["quality_score"], float) for record in fresh_records)
    assert all((out / "samples" / "sample_000001" / record["candidate_id"] / "meshes" / "ansa_oracle_mesh.bdf").is_file() for record in fresh_records)

    refreshed_training = run_quality_training(
        QualityTrainingConfig(
            dataset_root=dataset,
            quality_exploration_root=quality,
            extra_quality_evidence_roots=(out,),
            output_dir=RUNS / "fresh_run" / "training_refreshed",
            epochs=1,
            batch_size=8,
            seed=710,
        )
    )
    assert refreshed_training.status == "SUCCESS"
    assert refreshed_training.metrics["example_count"] > 2
    assert refreshed_training.metrics["extra_quality_evidence_roots"] == [out.as_posix()]


def test_fresh_source_boundaries() -> None:
    for relative in (
        "ai_mesh_generator/amg/recommendation/fresh.py",
        "ai_mesh_generator/amg/training/quality.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "import cad_dataset_factory" not in source
        assert "from cad_dataset_factory" not in source
        assert "reference_midsurface" not in source
        assert "target_action_id" not in source
        assert "target_edge_length_mm" not in source
