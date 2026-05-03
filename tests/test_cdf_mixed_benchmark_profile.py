from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from cad_dataset_factory.cdf.domain import FeatureRole, PartClass
from cad_dataset_factory.cdf.pipeline import e2e_dataset

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_mixed_benchmark_profile"


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_mixed_benchmark_profile_target_plan_is_closed_and_deterministic() -> None:
    cases = e2e_dataset._target_cases_for_profile(e2e_dataset.MIXED_BENCHMARK_PROFILE, 150)

    assert len(cases) == 150
    assert cases[:5] == [
        e2e_dataset.PROFILE_CASE_HOLE,
        e2e_dataset.PROFILE_CASE_SLOT,
        e2e_dataset.PROFILE_CASE_CUTOUT,
        e2e_dataset.PROFILE_CASE_COMBO,
        e2e_dataset.PROFILE_CASE_L_BRACKET,
    ]
    assert {case: cases.count(case) for case, _count in e2e_dataset.MIXED_BENCHMARK_CASE_COUNTS} == {
        case: count for case, count in e2e_dataset.MIXED_BENCHMARK_CASE_COUNTS
    }
    with pytest.raises(e2e_dataset.CdfPipelineError, match="invalid_profile_count"):
        e2e_dataset._target_cases_for_profile(e2e_dataset.MIXED_BENCHMARK_PROFILE, 149)


def test_family_expansion_profile_target_plan_is_closed_and_deterministic() -> None:
    cases = e2e_dataset._target_cases_for_profile(e2e_dataset.FAMILY_EXPANSION_PROFILE, 240)

    assert len(cases) == 240
    assert cases[:8] == [
        e2e_dataset.PROFILE_CASE_HOLE,
        e2e_dataset.PROFILE_CASE_SLOT,
        e2e_dataset.PROFILE_CASE_CUTOUT,
        e2e_dataset.PROFILE_CASE_COMBO,
        e2e_dataset.PROFILE_CASE_SINGLE_FLANGE,
        e2e_dataset.PROFILE_CASE_L_BRACKET,
        e2e_dataset.PROFILE_CASE_U_CHANNEL,
        e2e_dataset.PROFILE_CASE_HAT_CHANNEL,
    ]
    assert {case: cases.count(case) for case, _count in e2e_dataset.FAMILY_EXPANSION_CASE_COUNTS} == {
        case: count for case, count in e2e_dataset.FAMILY_EXPANSION_CASE_COUNTS
    }
    with pytest.raises(e2e_dataset.CdfPipelineError, match="invalid_profile_count"):
        e2e_dataset._target_cases_for_profile(e2e_dataset.FAMILY_EXPANSION_PROFILE, 239)


def test_mixed_profile_specs_cover_required_truth_cases() -> None:
    rng = __import__("random").Random(706)
    hole = e2e_dataset._flat_panel_spec("sample_000001", 1, rng, e2e_dataset.PROFILE_CASE_HOLE)
    slot = e2e_dataset._flat_panel_spec("sample_000031", 31, rng, e2e_dataset.PROFILE_CASE_SLOT)
    cutout = e2e_dataset._flat_panel_spec("sample_000061", 61, rng, e2e_dataset.PROFILE_CASE_CUTOUT)
    combo = e2e_dataset._flat_panel_spec("sample_000091", 91, rng, e2e_dataset.PROFILE_CASE_COMBO)
    l_bracket = e2e_dataset._bent_part_spec("sample_000121", 121, e2e_dataset.PROFILE_CASE_L_BRACKET)

    assert [feature.type.value for feature in hole.features] == ["HOLE"]
    assert [feature.type.value for feature in slot.features] == ["SLOT"]
    assert [feature.type.value for feature in cutout.features] == ["CUTOUT"]
    assert [feature.type.value for feature in combo.features] == ["HOLE", "SLOT", "CUTOUT"]
    assert cutout.features[0].role == FeatureRole.PASSAGE
    assert l_bracket.part_class == PartClass.SM_L_BRACKET
    assert l_bracket.flange_width_mm >= 2.0 * l_bracket.thickness_mm


def test_family_expansion_bent_specs_cover_required_part_classes() -> None:
    specs = {
        e2e_dataset.PROFILE_CASE_SINGLE_FLANGE: e2e_dataset._bent_part_spec(
            "sample_000001",
            1,
            e2e_dataset.PROFILE_CASE_SINGLE_FLANGE,
        ),
        e2e_dataset.PROFILE_CASE_L_BRACKET: e2e_dataset._bent_part_spec(
            "sample_000002",
            2,
            e2e_dataset.PROFILE_CASE_L_BRACKET,
        ),
        e2e_dataset.PROFILE_CASE_U_CHANNEL: e2e_dataset._bent_part_spec(
            "sample_000003",
            3,
            e2e_dataset.PROFILE_CASE_U_CHANNEL,
        ),
        e2e_dataset.PROFILE_CASE_HAT_CHANNEL: e2e_dataset._bent_part_spec(
            "sample_000004",
            4,
            e2e_dataset.PROFILE_CASE_HAT_CHANNEL,
        ),
    }

    assert specs[e2e_dataset.PROFILE_CASE_SINGLE_FLANGE].part_class == PartClass.SM_SINGLE_FLANGE
    assert specs[e2e_dataset.PROFILE_CASE_L_BRACKET].part_class == PartClass.SM_L_BRACKET
    assert specs[e2e_dataset.PROFILE_CASE_U_CHANNEL].part_class == PartClass.SM_U_CHANNEL
    assert specs[e2e_dataset.PROFILE_CASE_HAT_CHANNEL].part_class == PartClass.SM_HAT_CHANNEL
    assert specs[e2e_dataset.PROFILE_CASE_HAT_CHANNEL].side_wall_width_mm is not None


def test_mixed_profile_splits_are_non_empty_70_15_15() -> None:
    dataset_root = _fresh(RUNS / "splits")
    accepted = [{"sample_id": f"sample_{index:06d}"} for index in range(1, 151)]

    e2e_dataset._write_splits(dataset_root, accepted, e2e_dataset.MIXED_BENCHMARK_PROFILE)

    train = (dataset_root / "splits" / "train.txt").read_text(encoding="utf-8").splitlines()
    val = (dataset_root / "splits" / "val.txt").read_text(encoding="utf-8").splitlines()
    test = (dataset_root / "splits" / "test.txt").read_text(encoding="utf-8").splitlines()
    assert len(train) == 105
    assert len(val) == 22
    assert len(test) == 23
    assert train[0] == "sample_000001"
    assert test[-1] == "sample_000150"


def test_family_expansion_splits_are_non_empty_70_15_15() -> None:
    dataset_root = _fresh(RUNS / "family_splits")
    accepted = [{"sample_id": f"sample_{index:06d}"} for index in range(1, 241)]

    e2e_dataset._write_splits(dataset_root, accepted, e2e_dataset.FAMILY_EXPANSION_PROFILE)

    train = (dataset_root / "splits" / "train.txt").read_text(encoding="utf-8").splitlines()
    val = (dataset_root / "splits" / "val.txt").read_text(encoding="utf-8").splitlines()
    test = (dataset_root / "splits" / "test.txt").read_text(encoding="utf-8").splitlines()
    assert len(train) == 168
    assert len(val) == 36
    assert len(test) == 36
    assert train[0] == "sample_000001"
    assert test[-1] == "sample_000240"


def test_mixed_profile_probe_failure_blocks_generation(monkeypatch) -> None:
    dataset_root = _fresh(RUNS / "probe_blocked")
    fake_ansa = dataset_root / "ansa64.bat"
    fake_ansa.write_text("@echo off\n", encoding="utf-8")

    def fake_build_candidate_attempt(**kwargs) -> None:
        Path(kwargs["attempt_dir"]).mkdir(parents=True, exist_ok=True)

    def fake_run_ansa_oracle(*_args, **_kwargs):
        return SimpleNamespace(status="FAILED", error_code="probe_case_failed")

    monkeypatch.setattr(e2e_dataset, "_build_candidate_attempt", fake_build_candidate_attempt)
    monkeypatch.setattr(e2e_dataset, "run_ansa_oracle", fake_run_ansa_oracle)

    result = e2e_dataset.generate_dataset(
        config_path=ROOT / "configs" / "cdf_sm_ansa_v1.default.json",
        out_dir=dataset_root,
        count=150,
        seed=706,
        require_ansa=True,
        env={"ANSA_EXECUTABLE": str(fake_ansa)},
        profile=e2e_dataset.MIXED_BENCHMARK_PROFILE,
    )

    stats = json.loads((dataset_root / "dataset_stats.json").read_text(encoding="utf-8"))
    rejected = json.loads((dataset_root / "rejected" / "rejected_index.json").read_text(encoding="utf-8"))
    assert result.status == "BLOCKED"
    assert result.reason == "mixed_profile_probe_failed"
    assert stats["profile"] == e2e_dataset.MIXED_BENCHMARK_PROFILE
    assert stats["accepted_count"] == 0
    assert rejected["num_rejected"] == len(e2e_dataset.MIXED_BENCHMARK_REQUIRED_CASES)
    assert {item["profile_case"] for item in rejected["rejected_samples"]} == set(e2e_dataset.MIXED_BENCHMARK_REQUIRED_CASES)


def test_family_expansion_probe_failure_blocks_every_required_case(monkeypatch) -> None:
    dataset_root = _fresh(RUNS / "family_probe_blocked")
    fake_ansa = dataset_root / "ansa64.bat"
    fake_ansa.write_text("@echo off\n", encoding="utf-8")

    def fake_build_candidate_attempt(**kwargs) -> None:
        Path(kwargs["attempt_dir"]).mkdir(parents=True, exist_ok=True)

    def fake_run_ansa_oracle(*_args, **_kwargs):
        return SimpleNamespace(status="FAILED", error_code="probe_case_failed")

    monkeypatch.setattr(e2e_dataset, "_build_candidate_attempt", fake_build_candidate_attempt)
    monkeypatch.setattr(e2e_dataset, "run_ansa_oracle", fake_run_ansa_oracle)

    result = e2e_dataset.generate_dataset(
        config_path=ROOT / "configs" / "cdf_sm_ansa_v1.default.json",
        out_dir=dataset_root,
        count=240,
        seed=707,
        require_ansa=True,
        env={"ANSA_EXECUTABLE": str(fake_ansa)},
        profile=e2e_dataset.FAMILY_EXPANSION_PROFILE,
    )

    rejected = json.loads((dataset_root / "rejected" / "rejected_index.json").read_text(encoding="utf-8"))
    assert result.status == "BLOCKED"
    assert rejected["num_rejected"] == len(e2e_dataset.FAMILY_EXPANSION_REQUIRED_CASES)
    assert {item["profile_case"] for item in rejected["rejected_samples"]} == set(e2e_dataset.FAMILY_EXPANSION_REQUIRED_CASES)
