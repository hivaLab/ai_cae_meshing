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

Do not revive feature-action manifests, recommendation/ranker selection, baseline mesh
selection, quality-surrogate optimizer success, mock reports, or fabricated metrics.

## Current State

Completed:

- `T-806B_ENTITY_IDENTITY_REBASE`
- `T-809_DIRECT_BREP_SIZE_FIELD_MODEL`
- `T-810_ENTITY_LOCAL_BDF_METRIC_EXTRACTION`
- `T-806_ANSA_SIZE_FIELD_CONTROL_GATE`
- `T-811_REAL_AI_SIZE_FIELD_GATE`
- `T-812_DIVERSE_ENTITY_DATASET_AND_MODEL_VALIDATION`
- `T-813_ENTITY_MATCHING_AND_QUALITY_EVIDENCE_COVERAGE`
- `T-814_QUALITY_AWARE_SIZE_FIELD_LEARNING`
- `T-815_FULL_HELD_OUT_AI_ANSA_GATE`
- `T-816_PRIMARY_END_TO_END_COMMAND`
- `T-817_SEGMENTATION_AND_SIZE_EFFICIENCY_IMPROVEMENT`
- `T-818_DIVERSITY_FIRST_ENTITY_LEARNING_DATASET`

Latest regression:

```powershell
python -m pytest
```

```text
73 passed
```

## Learning Evidence To Preserve

T-818 diversity-first dataset:

```text
dataset: runs\t818_learning_balanced_dataset\dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 112
part_train/part_test: 84/28
segmentation_train/segmentation_test: 84/28
```

T-818 part classifier:

```text
part_test accuracy: 1.0
classes present: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET,
  SM_U_CHANNEL, SM_HAT_CHANNEL, OTHER
```

T-818 segmentation:

```text
segmentation_test face accuracy: 0.9016393442622951
segmentation_test edge accuracy: 0.8857644991212654
SLOT_BOUNDARY F1: 0.7111
OUTER_BOUNDARY F1: 0.2857
FREE_EDGE F1: 0.8378
CUTOUT_BOUNDARY F1: 0.5455
HOLE_BOUNDARY F1: 0.8333
BEND_EDGE F1: 0.9282
INTERNAL F1: 0.9867
```

## Next Task

Implement:

```text
T-819_BALANCED_ENTITY_SIZE_FIELD_REAL_GATE
```

## Required Work

1. Reconnect the T-818 balanced dataset to size-field learning.
   - Run efficiency-aware size sweeps on the T-818 train split.
   - Preserve pass, near-fail, fail, and blocked evidence.
   - Do not fabricate local quality metrics.
2. Train the three primary AMG models on the purpose-specific splits.
   - Part classifier: `part_train`, evaluate `part_test`.
   - Segmentation: `segmentation_train`, evaluate `segmentation_test`.
   - Size field: predicted part/segmentation context, quality evidence only on label side.
3. Run a real ANSA held-out size-field gate.
   - Include flat hole, slot, cutout/combo and bent-family samples.
   - Count success only with real execution reports, real quality reports, non-empty BDF,
     zero hard failed elements, and available entity-local metrics.
4. Preserve T-817 efficiency criteria.
   - Hole divisions practical.
   - Far-field edges remain coarse enough for efficient analysis.
   - Edge-size fields must not collapse to uniform h-min.

If the real gate fails, keep T-819 `IN_PROGRESS` and record exact sample ids, semantic
confusions, size-field distributions, ANSA report paths, and failure reasons. Do not hide
failure with baseline meshes, label-size substitution, or deterministic fallbacks.
