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
local artifact: removed during post-T817 cleanup; numeric evidence retained below
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
local artifact: removed during post-T817 cleanup; numeric evidence retained below
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
local artifact: removed during post-T817 cleanup; numeric evidence retained below
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

Status: `DONE`

Improve mesh efficiency and segmentation fidelity after the first full AI-to-ANSA closure.

Implemented:

- Efficiency-aware CDF size labels and `local_efficiency_v1` size sweeps.
- Class-balanced segmentation loss with per-class precision/recall/F1/confusion matrices.
- Predicted-context size-field training using the trained part classifier and segmentation
  model instead of label segmentation.
- Geometry-aware size-field projection that controls feature-local edges, avoids global
  far-field over-refinement, and filters unmeasurable midsurface duplicate curves.
- Efficiency-aware gate reporting for far-field size, hole divisions, shell count,
  h-min fraction, and per-semantic size statistics.

Real result:

```text
workflow: runs/t817_efficiency_validation/workflow_v7/workflow_report.json
attempted_count: 8
valid_mesh_count: 8
status_counts: SUCCESS=8
num_hard_failed_elements: 0 for every sample
h_min_edge_fraction_max: 0.0
edge_size_std_mean: 0.02807221164244637
flat-hole sample_000025:
  hole boundary divisions: 32
  far-field edge mean: 3.0 mm
  shell element count: 1191
  previous uniform-fine reference: 113171 elements
pytest: 72 passed
```

Remaining caveat:

This is a compact development gate. The held-out meshes are now much more efficient than
the first uniform-fine closure, but segmentation still needs broader data and stronger
generalization before production claims.

### T-818_DIVERSITY_FIRST_ENTITY_LEARNING_DATASET

Status: `DONE`

Created a compact diversity-first learning dataset that targets the weak part-class and
edge-segmentation classes directly instead of blindly increasing sample count.

Implemented:

- New CDF profile `sm_entity_v2_learning_balanced_v1`.
- 112 samples with flat feature-rich cases, bent-family cases, and clean `OTHER` examples.
- Purpose-specific splits: `part_train`, `part_test`, `segmentation_train`,
  `segmentation_test`, plus compatibility `train`/`test`.
- `label_coverage_report.json` with part/face/edge support by split.
- `--eval-split` for `amg-train-part-classifier` and `amg-train-entity-segmentation`.
- CAD-native summary features for the RandomForest part classifier.

Evidence:

```text
dataset: runs/t818_learning_balanced_dataset/dataset
sample_count: 112
python -m pytest: 73 passed
part_test accuracy: 1.0
segmentation_test face accuracy: 0.9016393442622951
segmentation_test edge accuracy: 0.8857644991212654
SLOT_BOUNDARY F1: 0.7111
OUTER_BOUNDARY F1: 0.2857
FREE_EDGE F1: 0.8378
CUTOUT_BOUNDARY F1: 0.5455
```

This closes the immediate diagnosis that the previous dataset had too little diversity
and weak rare-class support. It does not by itself prove a better ANSA mesh; that is the
next task.

### T-819_BALANCED_ENTITY_SIZE_FIELD_REAL_GATE

Status: `DONE`

Use the T-818 learning-balanced dataset for the real size-field gate. The goal is to
verify that improved part classification and segmentation accuracy translate into better
AI-predicted edge sizes and real ANSA meshes, while preserving T-817 efficiency criteria:

- no baseline/reference mesh success path
- real ANSA reports and non-empty BDFs
- all controlled entities have local metrics
- hole divisions and far-field efficiency remain bounded
- edge-size fields must not collapse to uniform h-min

Required work:

- Added `size_train` and `size_test` splits to `sm_entity_v2_learning_balanced_v1`.
- Ran `local_efficiency_v1` real ANSA sweep on `size_train`.
- Trained part classifier on `part_train`, segmentation on `segmentation_train`, and
  size field on `size_train` with predicted context and real quality evidence.
- Ran the real ANSA gate on `size_test`.
- Counted success only with real execution reports, quality reports, BDFs, and
  entity-local metrics.

Evidence:

```text
dataset: runs/t818_learning_balanced_dataset/dataset
size_train/size_test: 26/8
size sweep: attempted=130, completed=84, failed=46, blocked=0
workflow: runs/t819_balanced_size_field_gate/workflow_v3/workflow_report.json
workflow status: SUCCESS
valid_mesh_count: 8/8
part_test accuracy: 1.0
segmentation_test edge accuracy: 0.8769771528998243
size-field trained samples: 26/26
size-field target std: 3.0309552440652308 mm
h_min_edge_fraction_max: 0.0
hole divisions on flat-hole/combo samples: 32 practical divisions
pytest: 75 passed
```

No baseline/reference mesh, label-size substitution, fabricated metric, or mock ANSA
output is counted as success.

### T-820_PRODUCTION_PART_CLASSIFIER_AND_BREPNET_SEGMENTATION_UPGRADE

Status: `DONE`

Replaced the weak primary model stack for the two upstream perception tasks:

- Part classification now trains a CAD-native tabular ensemble and selects among
  RandomForest, ExtraTrees, and HistGradientBoosting.
- Face/edge segmentation now defaults to `BRepNetSegmentationModel`, a winged-edge
  coedge message-passing model with `next/prev/mate` walks.
- B-rep entity graph inputs now use `AMG_BREP_ENTITY_GRAPH_SM_V3` with richer geometry
  columns for surface type, curve type, loop position, face curve composition, closed
  loops, and dihedral hints.
- Active face segmentation classes were reduced from 8 to 7 by removing zero-support
  `BEND`; bend control remains represented by `BEND_EDGE`.
- A non-learnable flat boundary label bug was removed: `OUTER_BOUNDARY` versus
  `FREE_EDGE` no longer depends on edge index parity.

Evidence:

```text
dataset: runs/t820_brepnet_production_models/dataset
sample_count: 224
part selected model: ExtraTrees
part_test accuracy: 1.0
part per-class F1: 1.0 for all six classes
segmentation_test face accuracy: 0.9836065573770492
segmentation_test edge accuracy: 0.9850615114235501
OUTER_BOUNDARY F1: 1.0
HOLE_BOUNDARY F1: 1.0
SLOT_BOUNDARY F1: 0.888888888888889
CUTOUT_BOUNDARY F1: 0.8571428571428571
FREE_EDGE F1: 1.0
pytest: 75 passed
```

Downstream real ANSA smoke evidence:

```text
sample: sample_000126
status: COMPLETED
execution accepted: true
quality accepted: true
num_hard_failed_elements: 0
entity quality rows: 2/2 metric_available
max boundary size error: 0.009267542288650711
BDF bytes: 137913
```

Remaining caveat:

Rare slot/cutout wall and boundary classes improved but are not yet production-perfect.

### T-821_RARE_FEATURE_SEGMENTATION_AND_FACE_SIZE_CONTROL_HARDENING

Status: `TODO`

Next work:

- Increase slot/cutout wall and boundary reliability without reintroducing deterministic
  feature-label shortcuts into AMG.
- Add targeted geometry variation and harder held-out cases for slot and cutout walls.
- Pilot optional per-face size controls only where ANSA entity matching is reliable.
- Keep real ANSA reports, non-empty BDFs, zero hard failed elements, and entity-local
  metrics as the only success criteria.
