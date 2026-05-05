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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

Status: DONE

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

## P7_REAL_PIPELINE_COMPLETION

Status: IN_PROGRESS

Purpose:

```text
Move from contract/unit/smoke coverage to the AMG.md/CDF.md end-to-end pipeline:
CDF must generate ANSA-validated accepted samples, AMG must train from those accepted samples,
and AMG inference must produce a manifest that real ANSA can execute into a quality-passing mesh.
```

Non-negotiable completion rule:

```text
Do not mark a P7 task DONE from mocked ANSA reports, synthetic training targets, disabled oracle paths,
or unit/smoke tests alone. If real ANSA, accepted CDF samples, or real dataset labels are unavailable,
the task is BLOCKED or IN_PROGRESS, not DONE.
```

### T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED

Status: DONE

Goal:

```text
Implement the CDF generate/validate CLI orchestrator from CDF.md sections 19, 23, and 28,
using existing CAD generation, placement, graph extraction, truth matching, manifest writer,
aux label writer, sample writer, and ANSA runner boundaries.
```

Deliverables:

```text
cad_dataset_factory CLI entrypoint
cdf generate command
cdf validate command
dataset_stats.json writer
split file writer
fail-closed ANSA requirement handling
```

Acceptance:

```text
cdf generate --config configs/cdf_sm_ansa_v1.default.json --out runs/e2e_cdf --count 3 --seed 1 --require-ansa
  either creates 3 accepted samples with cad/input.step, graph/brep_graph.npz, labels/amg_manifest.json,
  reports/ansa_execution_report.json, reports/ansa_quality_report.json, meshes/ansa_oracle_mesh.bdf,
  reports/sample_acceptance.json accepted_by.ansa_oracle=true, and zero hard failed elements,
  or exits BLOCKED/FAILED with zero accepted samples when ANSA_EXECUTABLE/license is unavailable.
cdf validate --dataset runs/e2e_cdf rejects any sample missing real ANSA reports or oracle mesh.
No disabled-oracle, mock-oracle, synthetic-target, or placeholder accepted sample can be counted as accepted.
```

Required preconditions:

```text
ANSA executable and license must be available for the accepted-sample gate.
CadQuery/OCP must be available for CAD/STEP generation and B-rep extraction.
```

Completion evidence:

```text
Fail-closed CLI orchestration is implemented and the real ANSA gate created one
accepted sample with reports/ansa_execution_report.json accepted=true,
reports/ansa_quality_report.json accepted=true, zero hard failed elements, and
meshes/ansa_oracle_mesh.bdf. Strict cdf validate --require-ansa passed.
```

### T-702_CDF_REAL_ANSA_API_BINDING

Status: DONE

Goal:

```text
Replace the ANSA internal skeleton with real ANSA API bindings for import, cleanup,
midsurface extraction, manifest control application, batch meshing, quality report export,
solver deck export, and ANSA database export.
```

Acceptance:

```text
requires_ansa test imports one generated sample, executes the complete CDF.md 18.2 workflow,
writes schema-valid execution and quality reports, exports meshes/ansa_oracle_mesh.bdf,
and records accepted=false on quality failure instead of rewriting labels.
```

Required preconditions:

```text
Installed ANSA version scripting API documentation or introspection access.
ANSA_EXECUTABLE configured and runnable in batch/script mode.
```

Completion evidence:

```text
cdf ansa-probe succeeded against
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat.
ANSA internal script imports ansa/base/batchmesh/constants/mesh/session/utils,
runs STEP import, geometry cleanup, Skin midsurface extraction, batch mesh,
quality report writing, NASTRAN BDF export, and ANSA database export.
python -m pytest -m requires_ansa passed with the real ANSA executable.
```

### T-703_CDF_ACCEPTED_DATASET_PILOT

Status: DONE

Goal:

```text
Generate a real accepted CDF pilot dataset with ANSA oracle enabled and no mocked reports.
```

Acceptance:

```text
cdf generate produces at least 100 accepted samples with fixed seed and real ANSA execution.
cdf validate --require-ansa passes every accepted sample.
accepted samples have execution accepted=true, quality accepted=true,
num_hard_failed_elements=0, real non-empty BDF mesh, and no mock/unavailable/controlled-failure reports.
dataset_index.json, dataset_stats.json, rejected_index.json, splits, graph files, labels, meshes, and reports are complete.
dataset_stats records accepted_count, rejected_count, attempted_count, runtime, and rejection reason counts.
```

Required preconditions:

```text
T-701 and T-702 complete.
ANSA pass rate is high enough to finish within configured generation attempts.
```

Completion evidence:

```text
runs/pilot_cdf_100 contains 100 real ANSA-accepted samples.
cdf validate --dataset runs\pilot_cdf_100 --require-ansa returned SUCCESS with error_count=0.
dataset_stats.json records accepted_count=100, rejected_count=2, attempted_count=102,
runtime_sec=1234.132632, and rejection_reason_counts.feature_truth_matching_failed=2.
sample_000001 and sample_000100 both have execution accepted=true, quality accepted=true,
ANSA_v25.1.0, zero hard failed elements, and non-empty real BDF meshes.
```

Mathematical closure:

```text
Let A be the set of accepted sample ids in dataset_index.json.
T-703 is DONE only if |A| >= 100 and for every sample s in A:
  execution_s.accepted = true
  quality_s.accepted = true
  quality_s.num_hard_failed_elements = 0
  sample_acceptance_s.accepted_by.ansa_oracle = true
  size(mesh_s) > 0
  execution_s.ansa_version not in {unavailable, mock-ansa}
  controlled_failure_reason not in execution_s.outputs
If any predicate is false, s is not an accepted training sample.
```

### T-704_AMG_REAL_DATASET_TRAINING

Status: DONE

Goal:

```text
Train AMG on real CDF accepted samples using labels/amg_manifest.json as supervision,
not synthetic smoke targets or graph target columns.
```

Acceptance:

```text
AMG training CLI loads only accepted CDF samples through file contracts.
Loss uses manifest labels and graph candidate rows without target leakage columns.
Checkpoint, metrics, train/validation split results, and failure cases are written.
Training refuses to run on datasets without real ANSA-accepted samples.
```

Required preconditions:

```text
T-703 accepted pilot dataset exists.
Torch model dependency is installed.
```

Completion evidence:

```text
AMG real training ran on runs\pilot_cdf_100 using labels/amg_manifest.json supervision.
Output directory: runs\amg_training_real_pilot
Checkpoint: runs\amg_training_real_pilot\checkpoint.pt
Metrics: runs\amg_training_real_pilot\metrics.json
Training metrics record sample_count=100, candidate_count=100, manifest_feature_count=100,
matched_target_count=100, label_coverage_ratio=1.0, train_sample_count=80,
validation_sample_count=20, and split_source=deterministic_80_20_fallback.
python -m pytest passed with 186 passed and 1 skipped.
```

### T-705_AMG_REAL_INFERENCE_TO_ANSA_MESH

Status: DONE

Goal:

```text
Run AMG inference on held-out constant-thickness STEP inputs, project predictions to
AMG_MANIFEST_SM_V1, execute real ANSA, retry deterministically when applicable,
and produce solver-ready quality-passing meshes.
```

Acceptance:

```text
For a held-out validation set, AMG produces VALID_MESH outputs with solver deck and quality report.
Accepted mesh outputs have zero hard failed elements after retry.
Failures are explicit OUT_OF_SCOPE or MESH_FAILED reports with schema-valid reasons.
No mock adapter, disabled ANSA path, or deterministic-only fallback is counted as success.
```

Required preconditions:

```text
T-704 trained checkpoint exists.
T-702 real ANSA adapter path works.
Held-out validation STEP set is available.
```

Completion evidence:

```text
AMG real inference ran on the deterministic held-out subset from runs\pilot_cdf_100.
Command:
python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\pilot_cdf_100 --checkpoint runs\amg_training_real_pilot\checkpoint.pt --out runs\amg_inference_real_pilot --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --limit 20
Result: SUCCESS with attempted_count=20, success_count=20, failed_count=0, retry_count=0.
All held-out samples sample_000081 through sample_000100 have predicted AMG manifests,
real ANSA execution reports accepted=true, quality reports accepted=true,
num_hard_failed_elements=0, and non-empty BDF meshes.
python -m pytest passed with 195 passed and 1 skipped.
```

### T-706_REAL_PIPELINE_SCALE_UP_AND_GENERALIZATION_BENCHMARK

Status: DONE

Goal:

```text
Broaden the completed real AMG/CDF pilot beyond the current flat-panel single-hole distribution,
then report real ANSA first-pass/retry/failure metrics on unseen generated geometry.
```

Acceptance:

```text
CDF generates and validates a larger real ANSA-accepted dataset with mixed part families and feature types.
AMG trains on the expanded accepted manifest labels without target leakage.
AMG inference runs on an unseen held-out set through real ANSA.
Reports include sample counts, family/type coverage, first-pass VALID_MESH rate, retry success rate,
MESH_FAILED/OUT_OF_SCOPE reasons, hard failed element counts, and mesh artifact paths.
No mock, placeholder, disabled ANSA, deterministic rule fallback, or synthetic target path is counted as success.
```

Required preconditions:

```text
T-705 real inference gate is complete.
ANSA v25.1.0 executable/license remains available.
The current pilot limitations are recorded: mostly SM_FLAT_PANEL with one HOLE_UNKNOWN candidate per sample.
```

Completion evidence:

```text
Benchmark root: runs\t706_mixed_benchmark
Dataset: runs\t706_mixed_benchmark\dataset
Training: runs\t706_mixed_benchmark\training
Inference: runs\t706_mixed_benchmark\inference
Benchmark report: runs\t706_mixed_benchmark\benchmark_report.json

CDF generation command:
python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t706_mixed_benchmark\dataset --count 150 --seed 706 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_mixed_benchmark_v1
Result: SUCCESS, accepted_count=150, rejected_count=1.

CDF validation command:
python -m cad_dataset_factory.cdf.cli validate --dataset runs\t706_mixed_benchmark\dataset --require-ansa
Result: SUCCESS, accepted_count=150, error_count=0.

AMG training command:
python -m ai_mesh_generator.amg.training.real --dataset runs\t706_mixed_benchmark\dataset --out runs\t706_mixed_benchmark\training --epochs 10 --batch-size 16 --seed 706
Result: SUCCESS, label_coverage_ratio=1.0, candidate_count=240, manifest_feature_count=240.

AMG inference command:
python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t706_mixed_benchmark\dataset --checkpoint runs\t706_mixed_benchmark\training\checkpoint.pt --out runs\t706_mixed_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
Result: SUCCESS, attempted_count=23, success_count=23, failed_count=0.

Benchmark report command:
python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t706_mixed_benchmark\dataset --training runs\t706_mixed_benchmark\training --inference runs\t706_mixed_benchmark\inference --out runs\t706_mixed_benchmark\benchmark_report.json
Result: SUCCESS.

Coverage:
part_class histogram: SM_FLAT_PANEL=120, SM_L_BRACKET=30.
feature_type histogram: HOLE=60, SLOT=60, CUTOUT=60, BEND=30, FLANGE=30.
splits: train=105, val=22, test=23.
after-retry VALID_MESH rate: 1.0.
```

### T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS

Status: DONE

Goal:

```text
Expand the real pipeline benchmark beyond SM_FLAT_PANEL and SM_L_BRACKET to additional bent
families and harder feature combinations, while preserving fail-closed real ANSA validation.
```

Acceptance:

```text
CDF produces real ANSA-accepted samples for SM_SINGLE_FLANGE, SM_U_CHANNEL, and SM_HAT_CHANNEL
or records exact BLOCKED evidence for each unsupported family.
AMG trains and runs real ANSA inference on a held-out split from the expanded family dataset.
The benchmark report includes per-family VALID_MESH rate, failure histograms, and representative
ANSA reports for every failed family/feature combination.
No deterministic rule fallback, mock adapter, placeholder mesh, synthetic target, or skipped family is counted as success.
```

Completion evidence:

```text
Benchmark root: runs\t707_family_benchmark
Dataset: runs\t707_family_benchmark\dataset
Training: runs\t707_family_benchmark\training
Inference: runs\t707_family_benchmark\inference
Benchmark report: runs\t707_family_benchmark\benchmark_report.json

CDF generation command:
python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t707_family_benchmark\dataset --count 240 --seed 707 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_family_expansion_v1
Result: SUCCESS, accepted_count=240, rejected_count=1.

CDF validation command:
python -m cad_dataset_factory.cdf.cli validate --dataset runs\t707_family_benchmark\dataset --require-ansa
Result: SUCCESS, accepted_count=240, error_count=0.

AMG training command:
python -m ai_mesh_generator.amg.training.real --dataset runs\t707_family_benchmark\dataset --out runs\t707_family_benchmark\training --epochs 15 --batch-size 16 --seed 707
Result: SUCCESS, label_coverage_ratio=1.0, candidate_count=660, manifest_feature_count=660.

AMG inference command:
python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t707_family_benchmark\dataset --checkpoint runs\t707_family_benchmark\training\checkpoint.pt --out runs\t707_family_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
Result: SUCCESS, attempted_count=36, success_count=36, failed_count=0.

Benchmark report command:
python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t707_family_benchmark\dataset --training runs\t707_family_benchmark\training --inference runs\t707_family_benchmark\inference --out runs\t707_family_benchmark\benchmark_report.json --profile sm_family_expansion_v1
Result: SUCCESS.

Coverage:
part_class histogram: SM_FLAT_PANEL=120, SM_SINGLE_FLANGE=30, SM_L_BRACKET=30, SM_U_CHANNEL=30, SM_HAT_CHANNEL=30.
feature_type histogram: HOLE=60, SLOT=60, CUTOUT=60, BEND=240, FLANGE=240.
splits: train=168, val=36, test=36.
per-family after-retry VALID_MESH rate: 1.0 for every required part class.
```

### T-708_FAST_QUALITY_AWARE_DATASET_ITERATION

Status: DONE

Goal:

```text
Shift T-708 away from blind production-scale sample counts and toward fast,
quality-aware dataset iteration. Build a user-counted CDF profile with diverse
shape/control/action coverage, run real ANSA perturbation evaluations, and train
AMG to rank better and worse mesh-control manifests for the same geometry.
```

Acceptance:

```text
CDF profile sm_quality_exploration_v1 accepts arbitrary --count values and does not force 10,000 samples.
The profile diversifies part class, dimensions, thickness, feature size/position/count/role, bend radius/angle,
flange width, and manifest actions including KEEP_REFINED, KEEP_WITH_WASHER, SUPPRESS,
KEEP_WITH_BEND_ROWS, and KEEP_WITH_FLANGE_SIZE.
cdf quality-explore perturbs accepted baseline manifests, executes real ANSA, and records pass, fail,
near-fail, blocked, continuous quality metrics, and lower-is-better quality scores without overwriting labels.
Missing continuous ANSA quality metrics are BLOCKED for accepted meshes and are not guessed.
Real hard-failed ANSA reports with num_hard_failed_elements > 0 are recorded as FAILED labels even
when continuous statistics are unavailable.
amg-train-quality uses graph + manifest + quality exploration evidence by file contract only and trains
same-geometry pairwise ranking targets. Graph inputs contain no target action/control columns.
amg-quality-benchmark reports action/control entropy, quality score variance, pass/fail/near-fail counts,
pairwise ranking accuracy, and baseline-improvement evidence.
T-708 is DONE only after at least the real smoke gate completes:
  cdf generate --profile sm_quality_exploration_v1 --count 40 --require-ansa
  cdf quality-explore --perturbations-per-sample 3
  amg-train-quality
  amg-quality-benchmark
with nonzero control diversity, nonzero quality-score variance, both pass and fail/near-fail examples,
and held-out pairwise ranking accuracy above random baseline.
No mock, placeholder, unavailable ANSA, controlled failure, synthetic graph target, deterministic fallback,
or hidden skipped case can count as success.
```

Implemented so far:

```text
Code and unit/regression tests for the user-counted diversity profile, quality exploration runner,
continuous metric extraction from ANSA statistics HTML, quality-aware AMG ranker, and quality benchmark
report are implemented. Real ANSA control application is now bound for manifest edge length,
washer/refinement, suppression/fill, bend row, and flange sizing paths through the ANSA script boundary.
The ANSA statistics parser reads the Session-Parts quality table only, so element-count TOTAL rows
do not masquerade as violating shell counts.
Latest regression: python -m pytest -> 229 passed, 2 skipped in 10.54s.
```

Real smoke gate evidence:

```text
Command:
python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t708_quality_exploration_smoke\dataset --count 40 --seed 708 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_quality_exploration_v1
Result: SUCCESS, accepted_count=40, rejected_count=2.

Command:
python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
Result: SUCCESS, accepted_count=40, error_count=0.

Command:
python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
Original result before real control binding: SUCCESS, but same-geometry control response was not meaningful.

Command:
python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
Result: SUCCESS, baseline_count=40, evaluated_count=120, blocked_count=0, passed_count=84,
near_fail_count=40, failed_count=36, quality_score_variance=2814384.4276997964.

Command:
python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --out runs\t708_quality_exploration_smoke\training_quality_metricfix2 --epochs 5 --batch-size 32 --seed 708
Result: SUCCESS, validation_pairwise_accuracy=0.6666666666666666.

Command:
python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
Result: SUCCESS.

Quality benchmark evidence:
action_entropy_bits=2.272088893287269
feature_type_entropy_bits=2.28558992945765
control_value_variance=28.23013372004848
passed_count=84
near_fail_count=76
failed_count=36
blocked_count=0
quality_score_variance=2814384.4276997964
same_geometry_quality_delta_mean=1671.256000525
same_geometry_meaningful_delta_count=40
validation_pairwise_accuracy=0.6666666666666666
```

### T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA

Status: TODO

Goal:

```text
Use the T-708 quality ranker as an actual recommendation component: for held-out accepted geometries,
score candidate manifest controls, select the best predicted control manifest, run real ANSA, and compare
the resulting mesh quality against the baseline AMG manifest and a naive control baseline.
```

Acceptance:

```text
Input dataset and quality exploration artifacts are read by file contract only.
No CDF import, mock ANSA output, deterministic rule fallback, graph target columns, or reference_midsurface
model input can count toward success.
The recommender writes predicted AMG_MANIFEST_SM_V1 files and schema-valid per-sample comparison reports.
For a real smoke set, real ANSA executes baseline and recommended manifests, with non-empty BDF outputs.
The aggregate report includes baseline score, recommended score, improvement rate, failure histogram,
and paired same-geometry quality deltas.
T-709 is DONE only if the recommended manifest improves lower-is-better quality score over baseline
for a statistically meaningful fraction of attempted held-out samples, or it remains IN_PROGRESS with
the exact failure evidence and model/data bottleneck recorded.
```
