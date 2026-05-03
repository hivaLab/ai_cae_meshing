from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_mesh_generator.config import ConfigValidationError as AmgConfigValidationError
from ai_mesh_generator.config import load_amg_config
from ai_mesh_generator.config.load_config import _validate as validate_amg_config
from cad_dataset_factory.cdf.config import ConfigValidationError as CdfConfigValidationError
from cad_dataset_factory.cdf.config import load_cdf_config
from cad_dataset_factory.cdf.config.load_config import _validate as validate_cdf_config

ROOT = Path(__file__).resolve().parents[1]


def test_default_configs_validate() -> None:
    amg = load_amg_config()
    cdf = load_cdf_config()
    assert amg["unit"] == "mm"
    assert cdf["unit"] == "mm"


def test_missing_required_amg_key_raises_structured_error() -> None:
    data = json.loads((ROOT / "configs" / "amg_config.default.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "AMG_CONFIG_SM_V1.schema.json").read_text(encoding="utf-8"))
    data.pop("unit")
    with pytest.raises(AmgConfigValidationError) as exc_info:
        validate_amg_config(data, schema)
    assert exc_info.value.errors


def test_missing_required_cdf_key_raises_structured_error() -> None:
    data = json.loads((ROOT / "configs" / "cdf_sm_ansa_v1.default.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "CDF_CONFIG_SM_ANSA_V1.schema.json").read_text(encoding="utf-8"))
    data.pop("unit")
    with pytest.raises(CdfConfigValidationError) as exc_info:
        validate_cdf_config(data, schema)
    assert exc_info.value.errors
