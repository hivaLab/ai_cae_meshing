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

Status: `TODO`

Harden entity matching and sweep coverage so quality-aware size-field training uses all
profile cases, especially flat slot and duplicate-like boundary entities.
