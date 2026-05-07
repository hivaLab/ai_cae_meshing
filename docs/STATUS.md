# Project Status

## Current State

The active project is a B-rep entity AI meshing tool. Feature-action manifests,
recommendation/ranker loops, baseline mesh selection, mock reports, and fabricated
quality metrics are not active success paths.

Primary path:

```text
clean STEP CAD
  -> CDF B-rep entity graph and entity labels
  -> AMG part classifier
  -> AMG face/edge segmentation
  -> AMG direct segmentation-aware size-field GNN
  -> AMG_SIZE_FIELD_SM_V2
  -> real ANSA edge/face size controls
  -> BDF + real global and entity-local quality evidence
```

## Latest Completed Work

`T-820_PRODUCTION_PART_CLASSIFIER_AND_BREPNET_SEGMENTATION_UPGRADE` is complete as a
model-architecture and compact generated-CAD gate.

Implemented:

- Upgraded the entity graph contract to `AMG_BREP_ENTITY_GRAPH_SM_V3`.
- Added richer label-free face/edge/coedge features for BRepNet-style learning:
  surface type, curve type one-hots, face curve composition, loop/coedge position,
  closed-loop and dihedral hints.
- Removed zero-support `BEND` from the active face segmentation output; bend behavior
  remains represented by `BEND_EDGE`.
- Replaced the default compact segmentation MLP with a BRepNet-style winged-edge model
  using coedge `next/prev/mate` walks and face/edge pooling.
- Added part/global graph context and direct geometry heads to segmentation so flat
  outer edges and bent bend edges are learnable rather than conflated.
- Replaced the single RandomForest classifier with a CAD-native tabular ensemble
  selection over RandomForest, ExtraTrees, and HistGradientBoosting.
- Fixed a non-learnable CDF label bug where flat `OUTER_BOUNDARY` versus `FREE_EDGE`
  had been assigned by edge index parity.

Regression:

```powershell
python -m pytest
```

Result:

```text
75 passed
```

## T-820 Evidence

Dataset:

```text
runs/t820_brepnet_production_models/dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 224
```

Part classifier:

```text
train split: part_train
eval split: part_test
selected model: ExtraTrees
part_test accuracy: 1.0
uncertain_count: 0
all six part-class F1 values: 1.0
```

BRepNet-style segmentation:

```text
train split: segmentation_train
eval split: segmentation_test
model: BRepNetSegmentationModel
face classes: 7
edge classes: 8
face accuracy: 0.9836065573770492
edge accuracy: 0.9850615114235501
OUTER_BOUNDARY F1: 1.0
HOLE_BOUNDARY F1: 1.0
SLOT_BOUNDARY F1: 0.888888888888889
CUTOUT_BOUNDARY F1: 0.8571428571428571
FREE_EDGE F1: 1.0
```

Downstream real ANSA size-field gate smoke:

```text
sample: sample_000126
AI size field: runs/t820_brepnet_production_models/inference/sample_000126/amg_size_field_ai.json
ANSA evaluation: runs/t820_brepnet_production_models/ansa_eval/sample_000126
execution accepted: true
quality accepted: true
num_hard_failed_elements: 0
entity quality rows: 2/2 metric_available
hard_fail rows: 0
max boundary size error: 0.009267542288650711
BDF bytes: 137913
shell element count: 1300
```

## Active Task

`T-821_RARE_FEATURE_SEGMENTATION_AND_FACE_SIZE_CONTROL_HARDENING`

Why:

- The active model path is now the right one, but rare feature wall/boundary classes are
  not yet uniformly near-perfect.
- `SLOT_BOUNDARY`, `CUTOUT_BOUNDARY`, `SLOT_WALL`, and `CUTOUT_WALL` still need stronger
  per-class reliability before claiming production segmentation.
- Face size controls remain optional and have not yet been proven in the real ANSA gate.

## Known Gaps

1. The proof is generated clean CAD only; external industrial CAD generalization is not
   proven.
2. Face size controls remain optional; edge controls are the required path.
3. Rare feature segmentation is much improved but not yet near-100% per class.
4. The system assumes clean constant-thickness sheet-metal CAD; defeaturing remains out
   of scope.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
