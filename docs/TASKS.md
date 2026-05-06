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

Status: `TODO`

Train/infer the direct size-field model on compact v2 data, run ANSA with the predicted
`AMG_SIZE_FIELD_SM_V2`, and count success only if T-810 metrics are available and pass.

### T-812_DIVERSE_ENTITY_DATASET_AND_MODEL_VALIDATION

Status: `TODO`

After T-811 works on a smoke sample, expand to a compact diverse dataset with part
families, holes, slots, cutouts, bends, flanges, pass cases, near-fail cases, and fail
cases.
