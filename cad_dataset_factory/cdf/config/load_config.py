"""CDF config loader with JSON Schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class ConfigValidationError(ValueError):
    """Raised when a config file does not match its contract schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ConfigValidationError(messages)


def load_cdf_config(
    path: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    root = _repo_root()
    config_path = Path(path) if path is not None else root / "configs" / "cdf_sm_ansa_v1.default.json"
    schema_file = (
        Path(schema_path)
        if schema_path is not None
        else root / "contracts" / "CDF_CONFIG_SM_ANSA_V1.schema.json"
    )
    config = _read_json(config_path)
    schema = _read_json(schema_file)
    _validate(config, schema)
    return config
