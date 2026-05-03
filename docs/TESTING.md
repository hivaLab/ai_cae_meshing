# TESTING.md

## 1. Test categories

```text
unit_pure
  Formula, enum, schema, config, label rule tests. No CAD, no ANSA.

cad_kernel
  CadQuery/OCP generation and STEP export/import tests.

brep_graph
  B-rep extraction, coedge topology, feature candidate detection tests.

oracle_contract_negative
  ANSA command builder, parser, and validation rejection tests. No ANSA license required.
  These tests may use failed reports or mocks, but they cannot prove dataset acceptance.

requires_ansa
  Real ANSA runtime, oracle, dataset generation, and quality tests.
  Skipped unless ANSA_EXECUTABLE is configured.

model_smoke
  Dataset loader, batching, model forward/loss/checkpoint smoke tests.
```

## 2. Required commands

Baseline command:

```bash
python -m pytest
```

Pure tests only:

```bash
python -m pytest -m "not requires_ansa and not cad_kernel"
```

Real ANSA tests:

```bash
export ANSA_EXECUTABLE=/path/to/ansa64.sh
python -m pytest -m requires_ansa
```

## 3. Markers

`pyproject.toml` should define:

```toml
[tool.pytest.ini_options]
markers = [
  "cad_kernel: tests that require CadQuery/OCP STEP generation",
  "requires_ansa: tests that require a real ANSA executable/license",
  "model: tests that require ML framework components"
]
```

## 4. P0 required tests

```text
test_schema_files_are_valid_json
test_manifest_example_validates
test_make_even
test_clamp
test_curvature_formula
test_h0_formula
test_hole_label_rule
test_slot_label_rule
test_cutout_label_rule
test_bend_label_rule
test_flange_label_rule
test_smooth_log_sizes_bounds
test_smooth_log_sizes_growth_rate
test_no_amg_import_in_cdf
test_ansa_import_scope
test_graph_schema_has_no_target_action_column
```

## 5. CDF acceptance tests

```text
flat panel STEP export success
single flange constant thickness
L bracket bend radius
U channel two bends
hat channel four bends
no feature intersects boundary
no feature intersects bend
feature truth matching recall on smoke samples
sample directory contains all required files
labels/amg_manifest.json validates AMG_MANIFEST_SM_V1
```

## 6. AMG acceptance tests

```text
valid flat STEP produces VALID manifest
non-constant thickness produces OUT_OF_SCOPE
unknown role feature cannot be suppressed
hole washer downgrade occurs when clearance is insufficient
retry policy modifies only allowed controls
MESH_FAILED is produced after retry exhaustion
```

## 7. ANSA report parser and rejection tests

Use schema-valid failed JSON reports for parser and rejection cases:

```text
all pass
STEP import failure
midsurface extraction failure
entity matching failure
batch mesh failure
hard failed elements > 0
feature boundary size error too large
bend row error too large
controlled_failure_reason present
mock or unavailable ansa_version
placeholder mesh path
```

These fixtures must never be used as accepted dataset samples.

## 8. Quality gates by phase

```text
P0:
  all pure unit tests pass
  dependency boundary tests pass

P1:
  manifest/schema writer tests pass
  sample writer tests pass

P2:
  CAD smoke tests pass for flat panel and at least one bent family

P3:
  graph topology tests pass
  feature truth matching tests pass

P4:
  ANSA parser and rejection tests pass
  requires_ansa real one-sample gate passes when ANSA is configured

P5:
  AMG rule-only pipeline smoke passes

P6:
  dataset loader and model smoke tests pass

P7:
  cdf generate creates real ANSA-accepted samples
  cdf validate --require-ansa passes
  AMG training consumes only real accepted samples
  AMG inference-to-ANSA produces real quality-passing meshes or explicit MESH_FAILED/OUT_OF_SCOPE reports
```

## 9. Test data policy

```text
- Keep small deterministic fixtures under tests/fixtures/.
- Do not commit large generated datasets.
- Large datasets go under datasets/ and should be ignored by git unless explicitly packaged.
- Failed ANSA reports are allowed in tests/fixtures/ansa_reports/ for parser and rejection tests.
- Mock adapters and placeholder outputs are allowed only when a test asserts that production validation rejects them, or when testing AMG method mapping without claiming acceptance.
```
