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

Latest regression:

```powershell
python -m pytest
```

```text
72 passed
```

## Real Evidence To Preserve

T-817 efficiency workflow:

```text
workflow: runs\t817_efficiency_validation\workflow_v7\workflow_report.json
attempted_count: 8
valid_mesh_count: 8
success_count: 8
status_counts: SUCCESS=8
num_hard_failed_elements: 0 for every sample
h_min_edge_fraction_max: 0.0
edge_size_std_mean: 0.02807221164244637
```

Flat-hole sample evidence:

```text
sample: sample_000025
hole boundary divisions: 32
far-field edge mean: 3.0 mm
shell element count: 1191
previous uniform-fine reference: 113171 shell elements
```

Coverage:

```text
flat: sample_000025, sample_000026, sample_000027, sample_000028
bent: sample_000029, sample_000030, sample_000031, sample_000032
families: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
```

## Next Task

Implement:

```text
T-818_SCALE_ENTITY_DATA_AND_SEGMENTATION_GENERALIZATION
```

## Required Work

1. Scale the compact v2 dataset without changing the primary objective.
   - Keep user-controlled sample counts.
   - Preserve case-stratified train/test coverage.
   - Add more clean variations for holes, slots, cutouts, bends, flanges, thickness,
     clearances, and part dimensions.
2. Strengthen edge segmentation generalization.
   - Improve rare-class coverage for `SLOT_BOUNDARY`, `OUTER_BOUNDARY`, and `FREE_EDGE`.
   - Keep per-class confusion/F1 metrics as hard evidence.
3. Preserve T-817 efficiency criteria.
   - Hole divisions should remain in the practical range.
   - Far-field size should remain coarse enough for efficient analysis.
   - Edge-size fields must not collapse to uniform h-min.
4. Run a real ANSA gate on a larger but still development-sized held-out split.
   - Count success only with real execution reports, real quality reports, non-empty BDF,
     zero hard failed elements, and available entity-local metrics.

If the larger gate fails, keep T-818 `IN_PROGRESS` and record exact sample ids, semantic
confusions, size-field distributions, ANSA report paths, and failure reasons. Do not hide
failure with baseline meshes or deterministic fallbacks.
