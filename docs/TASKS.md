# Tasks

## Policy

Tasks are complete only when they advance the real CAD-native AI meshing objective.
Do not count mock meshes, reference meshes, baseline selection, hidden deterministic
fallbacks, or fabricated quality metrics as success.

## M8 B-rep Entity AI Meshing Rebuild

### T-800_DOCUMENTATION_REBASE_FOR_BREP_SIZE_FIELD_PIPELINE

Status: `DONE`

Documents were reset around clean CAD, part classification, B-rep segmentation, direct
entity size-field prediction, and real ANSA validation.

### T-801_BREP_ENTITY_DATA_CONTRACTS_AND_LABELS

Status: `DONE`

Implemented v2 graph, label, quality, and size-field contracts plus AMG entity loader.

### T-802_PART_CLASSIFIER_RF_MODEL

Status: `DONE`

Implemented `amg-train-part-classifier`.

### T-803_BREP_FACE_EDGE_SEGMENTATION_MODEL

Status: `DONE`

Implemented `amg-train-entity-segmentation`.

### T-804_ENTITY_QUALITY_SURROGATE_AND_SIZE_OPTIMIZER

Status: `SUPERSEDED`

The surrogate/optimizer route was removed from the active AMG surface. It does not
represent the primary target anymore.

### T-806B_ENTITY_IDENTITY_REBASE

Status: `DONE`

Implemented geometry fingerprints in `entity_signatures.json` and added
`cdf-entity ansa-probe-entities`.

Real evidence:

- ANSA probe found 17 `CONS` and 8 `FACE` entities for the smoke STEP.
- `CONS` exposes `Length`, `Start Point`, `End Point`, and `Min Radius`.
- Real size-field workflow now reaches `edge_match_count=17`.

### T-809_DIRECT_BREP_SIZE_FIELD_MODEL

Status: `DONE`

Implemented the primary direct size-field model:

- `BrepSizeFieldModel`
- `amg-train-size-field`
- `amg-infer-size-field`
- growth-rate projection into `AMG_SIZE_FIELD_SM_V2`

### T-806_ANSA_SIZE_FIELD_CONTROL_GATE

Status: `DONE`

The ANSA control path applies `AMG_SIZE_FIELD_SM_V2` edge controls, writes a real BDF,
and validates real local edge-size metrics for the smoke sample.

Real result:

```text
sample: runs/t806b_identity_probe_v3/dataset/samples/sample_000001
status: COMPLETED
edge_match_count: 10
entity quality rows: 10/10 metric_available
hard_fail rows: 0
max boundary size error: 0.012345679012345881
BDF bytes: 469274
```

### T-810_ENTITY_LOCAL_BDF_METRIC_EXTRACTION

Status: `DONE`

Implemented real local mesh metric extraction from exported NASTRAN BDF data.

Required output per controlled entity:

- measured boundary segment mean/min/max length
- measured boundary size error relative to target size
- metric availability reason if blocked
- hard/near-fail classification based on real measured values

### T-811_REAL_AI_SIZE_FIELD_GATE

Status: `DONE`

Train/infer the direct size-field model on compact v2 data, run ANSA with the predicted
`AMG_SIZE_FIELD_SM_V2`, and count success only if T-810 metrics are available and pass.

Real result:

```text
dataset: runs/t811_ai_size_field_gate/dataset
held-out sample: sample_000016
AI size field: runs/t811_ai_size_field_gate/inference/sample_000016/amg_size_field_ai.json
ANSA evaluation: runs/t811_ai_size_field_gate/ansa_eval/sample_000016
gate report: runs/t811_ai_size_field_gate/ai_size_field_gate_report.json
status: SUCCESS
entity quality rows: 24/24 metric_available
hard_fail rows: 0
max boundary size error: 0.0005120789403909587
BDF bytes: 34354036
```

Important caveat:

The first AI gate over-refined the held-out sample by predicting `0.5 mm` for every
controlled edge. This closes the real AI-to-ANSA path but does not prove efficient or
general meshing quality.

### T-812_DIVERSE_ENTITY_DATASET_AND_MODEL_VALIDATION

Status: `DONE`

After T-811 works on a smoke sample, expand to a compact diverse dataset with part
families, holes, slots, cutouts, bends, flanges, pass cases, near-fail cases, and fail
cases.

Real result:

```text
dataset: runs/t812_diverse_entity_validation/dataset
profile: sm_entity_v2_diverse_quality
sample count: 32
train/test split: 24/8, case-stratified
size sweep: 32 attempted, 17 completed, 3 mesh-quality failed, 12 blocked
blocked reason: entity_matching_failed on flat_slot cases
quality rows: 260 total, 248 metric_available
hard_fail rows: 18
near_fail rows: 18
pytest: 69 passed
```

Held-out AI gate evidence:

```text
flat sample: sample_000025
status: SUCCESS
edge sizes: count=10, min/mean/max/std=0.5/0.5899280985082083/0.625/0.04901566409509156
h_min fraction: 0.2
entity metrics: 10/10 available, hard_fail=0
max boundary size error: 0.004648606178533798
BDF bytes: 9528865

bent sample: sample_000032
status: SUCCESS
part class: SM_HAT_CHANNEL
edge sizes: count=24, min/mean/max/std=0.5/0.5449059218846366/0.625/0.05722437956992055
h_min fraction: 0.5
entity metrics: 24/24 available, hard_fail=0
max boundary size error: 0.008064516129032473
BDF bytes: 20326149
```

Important caveat:

T-812 proves non-h_min AI size fields can pass real ANSA on one flat and one bent held-out
sample. It does not yet prove broad generalization because only 5 train samples had usable
quality evidence and flat slot entity matching still blocks sweep coverage.

### T-813_ENTITY_MATCHING_AND_QUALITY_EVIDENCE_COVERAGE

Status: `DONE`

Rebased slot arc matching away from unstable center-point comparison and onto endpoint
pair, radius, curve plane, length, and fail-closed ambiguity checks.

Real evidence:

```text
fixed samples: sample_000002, sample_000010, sample_000018
previous blocker: entity_matching_failed on every flat slot sweep variant
after fix: blocked_count=0 for each flat slot sample
per slot sample sweep: 4 attempted, 3 completed, 1 mesh-quality failed
```

The remaining failed variants are real quality failures and remain label-side evidence;
they are not counted as hidden success.

### T-814_QUALITY_AWARE_SIZE_FIELD_LEARNING

Status: `DONE`

Strengthened quality-aware size-field training diagnostics. Training metrics now expose
usable sample count, skipped sample count, target-size histogram/statistics, target
standard deviation, h-min fraction, and `FAILED_LEARNING_SIGNAL` when targets collapse.

Real evidence:

```text
training output: runs/t813_entity_matching_closure/size_field
split: train
sample_count: 24
trained_sample_count: 8
skipped_sample_count: 16
edge target count: 110
edge target min/mean/max/std: 0.7875 / 3.1177 / 8.0 / 2.1553 mm
h_min edge fraction: 0.0
learning_signal_status: SUCCESS
```

### T-815_FULL_HELD_OUT_AI_ANSA_GATE

Status: `DONE`

Ran AI-predicted size fields through real ANSA on the entire 8-sample test split.

Real evidence:

```text
workflow: runs/t816_entity_ai_meshing_gate_v2/workflow_report.json
attempted_count: 8
valid_mesh_count: 8
status_counts: SUCCESS=8
num_hard_failed_elements: 0 for every sample
entity-local metrics: available for every controlled entity
BDF outputs: non-empty for every sample
edge_size_std_min: 0.000531993286870984
edge_size_std_mean: 0.03425069807954155
h_min_edge_fraction_max: 0.9615384615384616
```

Coverage:

```text
flat: sample_000025, sample_000026, sample_000027, sample_000028
bent: sample_000029, sample_000030, sample_000031, sample_000032
families: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
```

### T-816_PRIMARY_END_TO_END_COMMAND

Status: `DONE`

Added `amg-entity-size-field-gate`, the primary end-to-end runner for:

```text
train part classifier
train face/edge segmentation
train direct size-field model from quality evidence
infer AI size field on held-out samples
call cdf-entity ansa-evaluate-size-field via subprocess/file contract
write workflow_report.json and per-sample gate reports
```

AMG still does not import CDF Python modules. ANSA evaluation remains outside AMG and is
called through the CLI/file contract.

### T-817_SEGMENTATION_AND_SIZE_EFFICIENCY_IMPROVEMENT

Status: `TODO`

Improve mesh efficiency and segmentation fidelity after the first full AI-to-ANSA closure.

Motivation:

- The full gate succeeds on 8/8 held-out samples, but predicted edge sizes are still
  conservative: most controlled edges stay near `0.5..0.625 mm`.
- `h_min_edge_fraction_max` is `0.9615`, so one flat combo case is almost all h-min.
- Edge segmentation train accuracy is only about `0.70`, and flat samples still show
  semantically suspicious edge histograms such as `BEND_EDGE` predictions.

Next work should improve segmentation class balance, size-label construction, and
efficiency-aware loss so real ANSA success does not rely on heavy over-refinement.
