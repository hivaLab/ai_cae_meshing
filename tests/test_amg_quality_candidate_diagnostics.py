from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.diagnostics.quality_candidates import (
    QualityCandidateDiagnosticConfig,
    build_quality_candidate_diagnostics,
    main,
)
from test_amg_quality_recommendation import RUNS, ROOT, _write_fixture

pytestmark = pytest.mark.model


def test_quality_candidate_diagnostics_exposes_missing_better_ai_candidate() -> None:
    dataset, quality, _training = _write_fixture("candidate_diag")

    report = build_quality_candidate_diagnostics(
        QualityCandidateDiagnosticConfig(
            dataset_root=dataset,
            quality_exploration_root=quality,
            sample_ids=("sample_000001",),
        )
    )

    assert report["schema"] == "AMG_QUALITY_CANDIDATE_DIAGNOSTIC_V1"
    assert report["status"] == "NEEDS_IMPROVEMENT"
    sample = report["samples"][0]
    assert sample["status"] == "NEEDS_AI_CANDIDATE_IMPROVEMENT"
    assert sample["baseline_quality_score"] < sample["best_non_baseline_quality_score"]
    assert sample["candidate_count"] == 1
    assert sample["records"][0]["controls"]


def test_quality_candidate_diagnostics_cli_writes_report() -> None:
    dataset, quality, _training = _write_fixture("candidate_diag_cli")
    out = RUNS / "candidate_diag_cli" / "diagnostic.json"

    exit_code = main(
        [
            "--dataset",
            dataset.as_posix(),
            "--quality-exploration",
            quality.as_posix(),
            "--sample-id",
            "sample_000001",
            "--out",
            out.as_posix(),
        ]
    )

    assert exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "NEEDS_IMPROVEMENT"


def test_quality_candidate_diagnostics_source_boundaries() -> None:
    for relative in (
        "ai_mesh_generator/amg/diagnostics/quality_candidates.py",
        "ai_mesh_generator/amg/diagnostics/__init__.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "import cad_dataset_factory" not in source
        assert "from cad_dataset_factory" not in source
        assert "reference_midsurface" not in source
        assert "target_action_id" not in source
        assert "target_edge_length_mm" not in source
