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
- `T-819_BALANCED_ENTITY_SIZE_FIELD_REAL_GATE`

Latest regression:

```powershell
python -m pytest
```

```text
75 passed
```

## Real Evidence To Preserve

T-819 balanced real gate:

```text
dataset: runs\t818_learning_balanced_dataset\dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 112
part_train/part_test: 84/28
segmentation_train/segmentation_test: 84/28
size_train/size_test: 26/8
size sweep: attempted=130, completed=84, failed=46, blocked=0
workflow: runs\t819_balanced_size_field_gate\workflow_v3\workflow_report.json
workflow status: SUCCESS
valid_mesh_count: 8/8
part_test accuracy: 1.0
segmentation_test edge accuracy: 0.8769771528998243
size-field target std: 3.0309552440652308 mm
h_min_edge_fraction_max: 0.0
hole divisions on flat-hole/combo samples: 32 practical divisions
```

## Next Task

Implement:

```text
T-820_BALANCED_PROFILE_GENERALIZATION_AND_FACE_CONTROL_PILOT
```

## Required Work

1. Decide whether to run a larger balanced-profile multiple.
   - Recommended development next size: 224 samples, not 10,000.
   - Keep user-controlled counts.
2. Improve remaining segmentation weakness.
   - `OUTER_BOUNDARY` remains the weakest class.
   - Add targeted geometry or model changes only if they improve held-out F1 and real gate behavior.
3. Pilot optional face size controls.
   - Keep edge controls as the required success path.
   - Add face controls only for simple flat panels and bent webs where ANSA entity matching is reliable.
4. Preserve the T-819 real gate criteria.
   - No baseline/reference mesh success path.
   - No label-size substitution.
   - No fabricated local metrics.
   - Success requires real ANSA execution/quality reports, non-empty BDF, zero hard failed elements,
     and entity-local metric availability.

If the next gate fails, keep T-820 `IN_PROGRESS` and record exact sample ids, semantic
confusions, size-field distributions, ANSA report paths, and failure reasons.
