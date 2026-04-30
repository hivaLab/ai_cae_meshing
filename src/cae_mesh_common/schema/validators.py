from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"


class SchemaValidationError(ValueError):
    """Raised when an artifact fails JSON schema validation."""


def load_json_or_yaml(path: Path | str) -> Any:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(handle)
        return json.load(handle)


def load_schema(schema_name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / schema_name
    if not path.exists():
        raise FileNotFoundError(f"Unknown schema: {schema_name}")
    return load_json_or_yaml(path)


def validate_object(instance: Any, schema_name: str) -> None:
    schema = load_schema(schema_name)
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.path)
        prefix = f"{schema_name}:{location}" if location else schema_name
        raise SchemaValidationError(f"{prefix}: {exc.message}") from exc


def validate_json_file(path: Path | str, schema_name: str) -> dict[str, Any]:
    obj = load_json_or_yaml(path)
    validate_object(obj, schema_name)
    return obj


def validate_all_repository_schemas() -> dict[str, str]:
    results: dict[str, str] = {}
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        schema = load_json_or_yaml(path)
        jsonschema.Draft202012Validator.check_schema(schema)
        results[path.name] = "ok"
    return results
