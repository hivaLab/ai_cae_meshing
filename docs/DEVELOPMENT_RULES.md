# DEVELOPMENT_RULES.md

## 1. Python baseline

```text
Python version: >=3.11
Typing: required for public functions
Data models: pydantic v2 or dataclasses with explicit validation
JSON validation: jsonschema
Numerics: numpy/scipy where useful
Tests: pytest
```

## 2. Determinism

CDF generation must be reproducible from config and seed.

```text
- Use numpy random Generator, not global random state.
- Store config_used.json in dataset root.
- Store generator_params.json for every sample.
- Do not use wall-clock time in feature IDs or labels.
- Sample IDs are sequential and stable.
```

## 3. File writing rules

```text
- Write JSON with UTF-8 and stable key ordering when practical.
- Use relative paths inside dataset metadata.
- Do not overwrite accepted samples unless explicit --overwrite is passed.
- Write temporary files first, then atomic rename for final sample files when practical.
- Store failed/rejected records with structured reason.
```

## 4. Error handling

Public pipeline functions should return structured result objects or raise typed exceptions. Do not return ambiguous strings for pipeline state.

Recommended exception classes:

```text
ConfigurationError
SchemaValidationError
CadGenerationError
GeometryValidationError
FeatureMatchingError
ManifestRuleError
AnsaExecutionError
DatasetValidationError
```

Recommended result fields:

```text
accepted: bool
status: str
reason: str | null
message: str | null
artifacts: dict[str, str]
metrics: dict[str, float]
```

## 5. Formula implementation

Formulas from `AMG.md` and `CDF.md` must be implemented as pure functions with unit tests.

Examples:

```text
make_even
clamp
h0 computation
curvature size
hole divisions
washer radius projection
slot divisions
bend rows
flange target length
growth-rate smoothing
```

## 6. Naming

Use canonical names exactly.

```text
schema_version, not schema, for AMG manifest files
AMG_MANIFEST_SM_V1
AMG_CONFIG_SM_V1
AMG_FEATURE_OVERRIDES_SM_V1
AMG_QA_SHELL_V1
AMG_SHELL_CONST_THICKNESS_V1
```

CDF reports may use `schema` or `schema_version` only if their schema specifies it. Keep usage consistent per file.

## 7. Dependency constraints

```text
CDF core may not import AMG.
AMG dataset loader may not import CDF runtime modules.
ANSA API import is confined to ansa_scripts directories.
ANSA executable is configured by environment variable or config, not hardcoded.
```

## 8. Implementation style

```text
- Small modules with explicit responsibilities.
- No large hidden side effects in constructors.
- Avoid broad except clauses unless re-raising typed exceptions with reason.
- Prefer explicit enum classes over raw strings in Python internals.
- Serialize enum values as canonical strings.
- Keep CLI thin; call library functions from CLI.
```

## 9. Documentation update rule

Any change that affects behavior must update at least one of:

```text
STATUS.md
TASKS.md
CONTRACTS.md
DECISIONS.md
RISK_REGISTER.md
```

Schema or enum changes require updates to:

```text
CONTRACTS.md
contracts/*.schema.json
unit tests
DECISIONS.md if the change is architectural
```

## 10. Scope control

Features outside the current scope are recorded as future schema versions, not implemented silently.

Examples:

```text
louver/bead/emboss
assembly/contact/weld
solid tetra/hex meshing
variable thickness
CFD mesh target
solver physics validation
```
