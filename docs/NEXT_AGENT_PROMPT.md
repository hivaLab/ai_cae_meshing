# Next Agent Prompt

## Current Direction

Primary path:

```text
clean STEP CAD
  -> CDF B-rep entity graph
  -> AMG part classifier
  -> AMG face/edge segmentation
  -> AMG direct size-field GNN
  -> AMG_SIZE_FIELD_SM_V2
  -> real ANSA edge/face controls
  -> BDF + real entity-local quality metrics
```

Only count an AI-predicted `AMG_SIZE_FIELD_SM_V2` evaluated through real ANSA as
meshing success. Mock reports, reference artifacts, and fabricated metrics are invalid.

## Current State

Completed through:

```text
T-820_PRODUCTION_PART_CLASSIFIER_AND_BREPNET_SEGMENTATION_UPGRADE
```

Latest regression:

```powershell
python -m pytest
```

```text
72 passed
```

## Real Evidence To Preserve

T-820 generated-CAD model gate:

```text
dataset: runs\t820_brepnet_production_models\dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 224
part selected model: ExtraTrees
part_test accuracy: 1.0
part per-class F1: 1.0 for all six classes
segmentation model: BRepNetSegmentationModel
segmentation_test face accuracy: 0.9836065573770492
segmentation_test edge accuracy: 0.9850615114235501
OUTER_BOUNDARY F1: 1.0
HOLE_BOUNDARY F1: 1.0
SLOT_BOUNDARY F1: 0.888888888888889
CUTOUT_BOUNDARY F1: 0.8571428571428571
FREE_EDGE F1: 1.0
```

T-820 downstream real ANSA smoke:

```text
sample: sample_000126
AI size field: runs\t820_brepnet_production_models\inference\sample_000126\amg_size_field_ai.json
ANSA evaluation: runs\t820_brepnet_production_models\ansa_eval\sample_000126
execution accepted: true
quality accepted: true
num_hard_failed_elements: 0
entity quality rows: 2/2 metric_available
hard_fail rows: 0
max boundary size error: 0.009267542288650711
BDF bytes: 137913
shell element count: 1300
```

## Next Task

Implement:

```text
T-821_RARE_FEATURE_SEGMENTATION_AND_FACE_SIZE_CONTROL_HARDENING
```

## Required Work

1. Improve rare feature segmentation reliability.
   - `SLOT_BOUNDARY`, `CUTOUT_BOUNDARY`, `SLOT_WALL`, and `CUTOUT_WALL` are still below
     production-perfect per-class reliability.
   - Add targeted geometry variation and harder held-out slot/cutout cases.
   - Keep CDF labels learnable from geometry/topology; do not add label leakage columns.
2. Add explicit segmentation acceptance gates.
   - Fail if any active edge class has support but F1 remains near zero.
   - Keep `OUTER_BOUNDARY` as a hard metric.
3. Pilot optional face-size controls.
   - Edge controls remain the required success path.
   - Face controls may be added only for simple flat panels and bent webs where ANSA
     entity matching is stable.
4. Preserve the real ANSA criteria.
   - No reference-artifact success path.
   - No label-size substitution.
   - No fabricated local metrics.
   - Success requires real ANSA execution/quality reports, non-empty BDF, zero hard
     failed elements, and entity-local metric availability.

If the next gate fails, keep T-821 `IN_PROGRESS` and record exact sample ids, semantic
confusions, size-field distributions, ANSA report paths, and failure reasons.
