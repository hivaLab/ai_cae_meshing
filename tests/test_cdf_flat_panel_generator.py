from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.cadgen import (
    FlatPanelBuildError,
    FlatPanelFeatureSpec,
    FlatPanelSpec,
    build_flat_panel_part,
    write_flat_panel_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


def valid_spec() -> FlatPanelSpec:
    return FlatPanelSpec(
        sample_id="sample_000001",
        part_name="SMT_SM_FLAT_PANEL_T120_P000001",
        width_mm=160.0,
        height_mm=100.0,
        thickness_mm=1.2,
        features=[
            FlatPanelFeatureSpec(
                feature_id="HOLE_0001",
                type="HOLE",
                center_uv_mm=(35.0, 50.0),
                radius_mm=4.0,
            ),
            FlatPanelFeatureSpec(
                feature_id="SLOT_0001",
                type="SLOT",
                center_uv_mm=(80.0, 50.0),
                width_mm=8.0,
                length_mm=30.0,
            ),
            FlatPanelFeatureSpec(
                feature_id="CUTOUT_0001",
                type="CUTOUT",
                center_uv_mm=(125.0, 50.0),
                width_mm=20.0,
                height_mm=16.0,
            ),
        ],
    )


def test_valid_flat_panel_generates_solid_and_generator_metadata() -> None:
    pytest.importorskip("cadquery")

    generated = build_flat_panel_part(valid_spec())
    data = generated.generator_params

    assert generated.solid_shape is not None
    assert data["schema"] == "CDF_GENERATOR_PARAMS_SM_V1"
    assert data["sample_id"] == "sample_000001"
    assert data["part_class"] == "SM_FLAT_PANEL"
    assert data["W_mm"] == 160.0
    assert [feature["type"] for feature in data["features"]] == ["HOLE", "SLOT", "CUTOUT"]
    json.dumps(data)


def test_invalid_part_class_raises_flat_panel_build_error() -> None:
    spec = valid_spec().model_copy(update={"part_class": "SM_L_BRACKET"})

    with pytest.raises(FlatPanelBuildError) as exc_info:
        build_flat_panel_part(spec)
    assert exc_info.value.code == "unsupported_part_class"


def test_missing_width_or_height_raises_flat_panel_build_error() -> None:
    spec = valid_spec().model_copy(update={"width_mm": None})

    with pytest.raises(FlatPanelBuildError) as exc_info:
        build_flat_panel_part(spec)
    assert exc_info.value.code == "missing_panel_dimension"


def test_out_of_bounds_feature_raises_flat_panel_build_error() -> None:
    spec = valid_spec()
    spec.features[0].center_uv_mm = (2.0, 50.0)

    with pytest.raises(FlatPanelBuildError) as exc_info:
        build_flat_panel_part(spec)
    assert exc_info.value.code == "feature_out_of_bounds"
    assert exc_info.value.feature_id == "HOLE_0001"


def test_overlapping_features_raise_flat_panel_build_error() -> None:
    spec = valid_spec()
    spec.features[1].center_uv_mm = (38.0, 50.0)

    with pytest.raises(FlatPanelBuildError) as exc_info:
        build_flat_panel_part(spec)
    assert exc_info.value.code == "feature_overlap"
    assert exc_info.value.feature_id == "SLOT_0001"


def test_nonzero_slot_or_cutout_angle_raises_flat_panel_build_error() -> None:
    spec = valid_spec()
    spec.features[1].angle_deg = 15.0

    with pytest.raises(FlatPanelBuildError) as exc_info:
        build_flat_panel_part(spec)
    assert exc_info.value.code == "unsupported_feature_angle"
    assert exc_info.value.feature_id == "SLOT_0001"


@pytest.mark.cad_kernel
def test_cadquery_step_smoke_exports_and_reimports_flat_panel() -> None:
    cq = pytest.importorskip("cadquery")
    generated = build_flat_panel_part(valid_spec())
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_flat_panel_generator" / "samples" / "sample_000001"

    paths = write_flat_panel_outputs(sample_root, generated)

    input_step = Path(paths["input_step"])
    generator_params = Path(paths["generator_params"])

    for path in (input_step, generator_params):
        assert path.is_file()
        assert path.stat().st_size > 0
    assert not any("midsurface" in key or "truth" in key for key in paths)

    imported = cq.importers.importStep(str(input_step))
    assert imported.val().BoundingBox().zlen == pytest.approx(1.2, rel=0.05)

    params = json.loads(generator_params.read_text(encoding="utf-8"))
    assert params["schema"] == "CDF_GENERATOR_PARAMS_SM_V1"
