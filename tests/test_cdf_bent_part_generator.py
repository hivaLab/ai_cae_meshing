from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.cadgen import (
    BentPartBuildError,
    BentPartSpec,
    build_bent_part,
    write_bent_part_outputs,
)
from cad_dataset_factory.cdf.domain import PartClass

ROOT = Path(__file__).resolve().parents[1]


def bent_spec(part_class: PartClass = PartClass.SM_L_BRACKET) -> BentPartSpec:
    return BentPartSpec(
        sample_id="sample_000201",
        part_name=f"SMT_{part_class.value}_T120_P000201",
        part_class=part_class,
        length_mm=90.0,
        web_width_mm=48.0,
        flange_width_mm=24.0,
        side_wall_width_mm=22.0,
        thickness_mm=1.2,
        inner_radius_mm=1.2,
        bend_angle_deg=90.0,
    )


@pytest.mark.parametrize(
    ("part_class", "expected_bends", "expected_flanges"),
    [
        (PartClass.SM_SINGLE_FLANGE, 1, 1),
        (PartClass.SM_L_BRACKET, 1, 1),
        (PartClass.SM_U_CHANNEL, 2, 2),
        (PartClass.SM_HAT_CHANNEL, 4, 4),
    ],
)
def test_bent_part_generates_truth_for_all_supported_classes(
    part_class: PartClass,
    expected_bends: int,
    expected_flanges: int,
) -> None:
    pytest.importorskip("cadquery")

    generated = build_bent_part(bent_spec(part_class))
    data = generated.feature_truth.model_dump(mode="json")
    json.dumps(data)

    assert data["schema_version"] == "CDF_FEATURE_TRUTH_SM_V1"
    assert data["part"]["part_class"] == part_class.value
    bends = [feature for feature in data["features"] if feature["type"] == "BEND"]
    flanges = [feature for feature in data["features"] if feature["type"] == "FLANGE"]
    assert len(bends) == expected_bends
    assert len(flanges) == expected_flanges
    assert all(feature["role"] == "STRUCTURAL" for feature in data["features"])
    assert all(feature["created_by"] == "cadgen.bent_part.bend" for feature in bends)
    assert all(feature["created_by"] == "cadgen.bent_part.flange" for feature in flanges)
    assert bends[0]["feature_id"] == "BEND_STRUCTURAL_0001"
    assert flanges[0]["feature_id"] == "FLANGE_STRUCTURAL_0001"


def test_invalid_part_class_raises_bent_part_build_error() -> None:
    spec = bent_spec().model_copy(update={"part_class": PartClass.SM_FLAT_PANEL})

    with pytest.raises(BentPartBuildError) as exc_info:
        build_bent_part(spec)
    assert exc_info.value.code == "unsupported_part_class"


def test_invalid_bend_radius_raises_bent_part_build_error() -> None:
    spec = bent_spec().model_copy(update={"inner_radius_mm": 0.2})

    with pytest.raises(BentPartBuildError) as exc_info:
        build_bent_part(spec)
    assert exc_info.value.code == "invalid_bend_radius"


def test_invalid_bend_angle_raises_bent_part_build_error() -> None:
    spec = bent_spec().model_copy(update={"bend_angle_deg": 130.0})

    with pytest.raises(BentPartBuildError) as exc_info:
        build_bent_part(spec)
    assert exc_info.value.code == "invalid_bend_angle"


def test_invalid_flange_width_raises_bent_part_build_error() -> None:
    spec = bent_spec().model_copy(update={"flange_width_mm": 1.0})

    with pytest.raises(BentPartBuildError) as exc_info:
        build_bent_part(spec)
    assert exc_info.value.code == "invalid_flange_width"


@pytest.mark.cad_kernel
def test_cadquery_step_smoke_exports_and_reimports_l_bracket() -> None:
    cq = pytest.importorskip("cadquery")
    generated = build_bent_part(bent_spec(PartClass.SM_L_BRACKET))
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_bent_part_generator" / "samples" / "sample_000201"

    paths = write_bent_part_outputs(sample_root, generated)

    input_step = Path(paths["input_step"])
    midsurface_step = Path(paths["reference_midsurface_step"])
    feature_truth = Path(paths["feature_truth"])
    generator_params = Path(paths["generator_params"])

    for path in (input_step, midsurface_step, feature_truth, generator_params):
        assert path.is_file()
        assert path.stat().st_size > 0

    imported = cq.importers.importStep(str(input_step))
    bbox = imported.val().BoundingBox()
    assert bbox.xlen == pytest.approx(90.0, rel=0.05)
    assert bbox.ylen > 40.0
    assert bbox.zlen > 20.0

    truth = json.loads(feature_truth.read_text(encoding="utf-8"))
    assert truth["features"][0]["type"] == "BEND"
    params = json.loads(generator_params.read_text(encoding="utf-8"))
    assert params["schema"] == "CDF_GENERATOR_PARAMS_SM_V1"
