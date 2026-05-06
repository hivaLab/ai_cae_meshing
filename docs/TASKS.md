# Tasks

## Policy

Tasks must advance real CAD-native AI meshing. Do not mark a task complete from a
message, mock mesh, reference mesh selection, or hidden rule path.

## M8 B-rep Entity AI Meshing Rebuild

### T-800_DOCUMENTATION_REBASE_FOR_BREP_SIZE_FIELD_PIPELINE

Status: `DONE`

Project documents were reset around part classification, face/edge segmentation,
entity-local quality prediction, constrained size-field optimization, and ANSA real
validation.

### T-801_BREP_ENTITY_DATA_CONTRACTS_AND_LABELS

Status: `DONE`

Implemented v2 graph, label, quality, and size-field contracts plus AMG entity loader.

### T-802_PART_CLASSIFIER_RF_MODEL

Status: `DONE`

Implemented `amg-train-part-classifier`.

Completion evidence:

- trains from CDF v2 entity samples
- writes `model.pkl`, `metrics.json`, `confusion_matrix.json`
- exposes uncertainty threshold behavior

### T-803_BREP_FACE_EDGE_SEGMENTATION_MODEL

Status: `DONE`

Implemented `amg-train-entity-segmentation`.

Completion evidence:

- B-rep coedge-aware face/edge segmentation model exists
- trains on v2 face/edge segmentation labels
- writes `model.pt` and `metrics.json`

### T-804_ENTITY_QUALITY_SURROGATE_AND_SIZE_OPTIMIZER

Status: `DONE`

Implemented `amg-train-quality-surrogate` and `amg-optimize-size-field`.

Completion evidence:

- trains on `CDF_ENTITY_QUALITY_EVALUATION_SM_V2`
- optimizes `AMG_SIZE_FIELD_SM_V2`
- enforces size bounds and user growth-rate projection

### T-805_DIRECT_BREP_SIZE_FIELD_MODEL_DISTILLATION

Status: `DEFERRED`

Direct GNN size regression remains deferred until the quality-surrogate optimizer has
real ANSA entity-quality labels.

### T-806_ANSA_SIZE_FIELD_CONTROL_GATE

Status: `IN_PROGRESS`

Implement the real ANSA binding for:

```text
AMG_SIZE_FIELD_SM_V2 -> ANSA edge/face target size controls -> BDF + quality report
```

Done only when real reports, local metrics, zero hard failed elements, and non-empty BDF
exist for held-out samples.

Current implementation state:

- normal Python runner and ANSA internal script exist
- process return code is post-validated against reports, BDF, and entity metrics
- fake-adapter tests cover successful size application and blocked matching
- real ANSA gate ran once and correctly returned `BLOCKED`

Current blocker:

```text
entity_matching_failed
```

The ANSA v25.1.0 path exposes the expected number of edge entities for the smoke STEP,
but the attempted descriptor API returns unusable per-edge data (`length=-1.0`, no
center/bbox). T-806 remains open until stable ANSA descriptor extraction enables explicit
CDF edge/face signature matching and measured local quality rows.

### T-807_FAST_DIVERSE_ENTITY_DATASET_LOOP

Status: `TODO`

Generate compact diverse v2 data with pass, near-fail, and fail entity quality evidence.

### T-808_REAL_AI_MESHING_END_TO_END_GATE

Status: `TODO`

Run the full v2 path on held-out clean CAD with no reference mesh success path.
