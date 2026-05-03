# TASKS.md

Status values:

```text
TODO
IN_PROGRESS
DONE
BLOCKED
DEFERRED
```

## P0_BOOTSTRAP_CONTRACTS_AND_RULES

Status: DONE

### T-001_REPOSITORY_SKELETON

Status: DONE

Goal:

```text
Create initial workspace layout for AMG, CDF, contracts, configs, and tests.
```

Deliverables:

```text
pyproject.toml
contracts/
configs/
ai_mesh_generator/
cad_dataset_factory/
tests/
```

Acceptance:

```text
python -m pytest can run and discover tests
packages import with empty modules
README/AGENT docs remain at repository root
```

### T-002_CONTRACT_SCHEMA_SKELETON

Status: DONE

Goal:

```text
Create JSON schema skeletons for shared contracts.
```

Deliverables:

```text
contracts/AMG_MANIFEST_SM_V1.schema.json
contracts/AMG_BREP_GRAPH_SM_V1.schema.json
contracts/AMG_CONFIG_SM_V1.schema.json
contracts/AMG_FEATURE_OVERRIDES_SM_V1.schema.json
contracts/CDF_CONFIG_SM_ANSA_V1.schema.json
contracts/CDF_FEATURE_TRUTH_SM_V1.schema.json
contracts/CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json
contracts/CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json
```

Acceptance:

```text
schema files are valid JSON Schema Draft 2020-12 or Draft 7
example manifest from CONTRACTS.md validates
allowed enum values match CONTRACTS.md exactly
```

### T-003_CONFIG_SCHEMA_AND_DEFAULTS

Status: DONE

Goal:

```text
Create default configs and validation loaders.
```

Deliverables:

```text
configs/amg_config.default.json
configs/cdf_sm_ansa_v1.default.json
configs/quality/AMG_QA_SHELL_V1.json
configs/ansa/AMG_SHELL_CONST_THICKNESS_V1.json
cad_dataset_factory/cdf/config/load_config.py
ai_mesh_generator/config/load_config.py
```

Acceptance:

```text
configs validate against their schemas
missing required keys raise structured error
unit is fixed to mm in v1 configs
```

### T-004_MATH_UTILITIES

Status: DONE

Goal:

```text
Implement pure math utility functions used by AMG and CDF label rules.
```

Deliverables:

```text
common or duplicated package-local utilities:
  clamp
  make_even
  safe_ceil
  chord_error_size
  smooth_log_sizes
```

Acceptance:

```text
test_make_even
test_clamp
test_chord_error_formula
test_smooth_log_sizes_bounds
test_smooth_log_sizes_growth_rate
```

### T-005_LABEL_RULES_PURE

Status: DONE

Goal:

```text
Implement deterministic AMG-compatible label rules for HOLE, SLOT, CUTOUT, BEND, FLANGE.
```

Deliverables:

```text
cad_dataset_factory/cdf/labels/sizing.py
cad_dataset_factory/cdf/labels/amg_rules.py
ai_mesh_generator/labels/rule_manifest.py
```

Acceptance:

```text
HOLE BOLT/MOUNT -> KEEP_WITH_WASHER when clearance allows
HOLE UNKNOWN -> KEEP_REFINED
RELIEF/DRAIN suppression requires allow_small_feature_suppression=true and size rule pass
BEND -> KEEP_WITH_BEND_ROWS
FLANGE -> KEEP_WITH_FLANGE_SIZE
all target sizes satisfy h_min <= h <= h_max
```

### T-006_DEPENDENCY_BOUNDARY_TESTS

Status: DONE

Goal:

```text
Add tests that enforce CDF/AMG and ANSA dependency boundaries.
```

Deliverables:

```text
tests/test_dependency_boundary.py
```

Acceptance:

```text
CDF source contains no 'import amg' or 'from amg'
ANSA API import appears only in ansa_scripts directories
pytest passes without ANSA installed
```

## P1_CDF_RULE_LABEL_ENGINE_AND_FILE_WRITER

### T-101_CDF_DOMAIN_MODELS

Status: DONE

Goal:

```text
Create typed data models for part params, feature truth, entity signatures, mesh policy, manifest controls.
```

Acceptance:

```text
models serialize to JSON-compatible dictionaries
schema_version fields are present
invalid enum values raise validation errors
```

### T-102_CDF_MANIFEST_WRITER

Status: DONE

Goal:

```text
Write AMG_MANIFEST_SM_V1 from CDF params/truth/rules.
```

Acceptance:

```text
labels/amg_manifest.json matches schema
feature records include geometry_signature and controls
status is VALID for generated valid samples
```

### T-103_CDF_AUX_LABEL_WRITERS

Status: DONE

Goal:

```text
Write face_labels.json, edge_labels.json, feature_labels.json.
```

Acceptance:

```text
auxiliary labels match manifest feature ids
no auxiliary label is required for inference
```

### T-104_CDF_SAMPLE_WRITER

Status: DONE

Goal:

```text
Create sample directory writer and index writer.
```

Acceptance:

```text
sample_000001 directory structure matches DATASET.md
relative paths are stable
sample_acceptance.json records accepted_by booleans
```

## P2_CDF_CAD_GENERATION

### T-201_FLAT_PANEL_GENERATOR

Status: DONE

Goal:

```text
Generate constant-thickness flat panel solids with optional holes, slots, cutouts.
```

Acceptance:

```text
STEP export succeeds for smoke samples
reference_midsurface.step is generated
feature_truth.json records generated features
```

### T-202_BENT_PART_GENERATORS

Status: DONE

Goal:

```text
Generate single flange, L bracket, U channel, hat channel solids.
```

Acceptance:

```text
bend and flange truth records generated
constant thickness validator passes
bend radius constraints enforced
```

### T-203_FEATURE_PLACEMENT_SAMPLER

Status: DONE

Goal:

```text
Implement feature layout sampling with clearance constraints.
```

Acceptance:

```text
boundary clearance passes
feature-feature clearance passes
bend clearance passes
resampling terminates or returns structured rejection reason
```

## P3_BREP_GRAPH_AND_MATCHING

### T-301_BREP_GRAPH_EXTRACTOR

Status: DONE

Goal:

```text
Extract PART/FACE/EDGE/COEDGE/VERTEX/FEATURE_CANDIDATE graph from STEP.
```

Acceptance:

```text
graph_schema.json lists column order
coedge cycles validate
adjacency arrays are saved in brep_graph.npz
```

### T-302_FEATURE_CANDIDATE_DETECTOR

Status: TODO

Goal:

```text
Detect HOLE, SLOT, CUTOUT, BEND, FLANGE candidates deterministically.
```

Acceptance:

```text
circular through holes detected by loop fit
slots detected by line+arc structure
bends detected by cylindrical/near-cylindrical strip
```

### T-303_TRUTH_MATCHING_REPORT

Status: TODO

Goal:

```text
Match CDF truth features to detected B-rep candidates by stable geometry signatures.
```

Acceptance:

```text
truth recall is 100% for accepted generated smoke samples
false match count is 0 for accepted samples
feature_matching_report.json schema validates
```

## P4_ANSA_ORACLE

### T-401_ANSA_COMMAND_RUNNER

Status: TODO

Goal:

```text
Build subprocess command for ANSA batch execution and timeout handling.
```

Acceptance:

```text
command builder test passes without ANSA
missing ANSA_EXECUTABLE produces structured skip/error
```

### T-402_ANSA_INTERNAL_SCRIPT_SKELETON

Status: TODO

Goal:

```text
Create cdf_ansa_oracle.py and API-layer placeholders to be bound to installed ANSA version.
```

Acceptance:

```text
script reads sample paths and manifest
script writes ansa_execution_report.json even on controlled failure
ANSA imports are confined to ansa_scripts
```

### T-403_ANSA_REPORT_PARSER

Status: TODO

Goal:

```text
Parse ANSA execution and quality reports into typed objects.
```

Acceptance:

```text
mock report pass/fail tests pass
quality hard fail count is extracted
feature boundary errors are extracted
```

## P5_AMG_RULE_ONLY_PIPELINE

### T-501_AMG_INPUT_VALIDATION

Status: TODO

Goal:

```text
Validate input.step, amg_config.json, feature_overrides.json and produce OUT_OF_SCOPE when needed.
```

Acceptance:

```text
single connected solid check path exists
constant thickness validator path exists
midsurface pairing validator path exists
failure manifests use AMG_MANIFEST_SM_V1
```

### T-502_AMG_DETERMINISTIC_MANIFEST

Status: TODO

Goal:

```text
Generate manifest from detected features and rules without AI model.
```

Acceptance:

```text
manifest validates schema
UNKNOWN features are not suppressed
growth-rate smoothing is applied
```

### T-503_AMG_ANSA_ADAPTER_INTERFACE

Status: TODO

Goal:

```text
Create AMG AnsaAdapter interface and manifest runner skeleton.
```

Acceptance:

```text
adapter interface matches AMG.md
mock adapter can simulate success/failure
retry policy has unit tests
```

## P6_AMG_MODEL_BASELINE

### T-601_DATASET_LOADER

Status: TODO

Goal:

```text
Load CDF dataset files without importing CDF package.
```

Acceptance:

```text
loader reads graph/brep_graph.npz and labels/amg_manifest.json
schema versions are checked
reference_midsurface.step is not used as model input
```

### T-602_MODEL_SKELETON

Status: TODO

Goal:

```text
Create B-rep graph model skeleton with output heads.
```

Acceptance:

```text
feature action head supports mask
numeric heads output log sizes/divisions
model output passes rule projector before manifest serialization
```

### T-603_TRAINING_LOOP_SMOKE

Status: TODO

Goal:

```text
Run a small training-loop smoke test on synthetic mocked graph data.
```

Acceptance:

```text
loss computes without NaN
checkpoint save/load works
metrics are reported
```
