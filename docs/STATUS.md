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

`T-817_SEGMENTATION_AND_SIZE_EFFICIENCY_IMPROVEMENT` is complete.

What changed:

- Added efficiency-aware CDF size labeling and `local_efficiency_v1` sweep variants.
- Added class-balanced segmentation training with per-class confusion/F1 metrics.
- Trained size-field models with predicted part/segmentation context, matching inference.
- Added geometry-aware size-field projection so feature-local edges are refined while
  global far-field edges use the global size instead of explicit fine edge controls.
- Filtered unmeasurable midsurface duplicate curves out of ANSA edge controls.
- Added efficiency gate reporting for far-field size, hole divisions, shell element
  count, h-min fraction, and semantic size statistics.

Regression:

```powershell
python -m pytest
```

Result:

```text
72 passed
```

## Real ANSA Evidence

Workflow:

```text
runs/t817_efficiency_validation/workflow_v7/workflow_report.json
```

Summary:

```text
attempted_count: 8
valid_mesh_count: 8
success_count: 8
status_counts: SUCCESS=8
num_hard_failed_elements: 0 for every sample
entity-local metrics: available for every controlled entity
h_min_edge_fraction_max: 0.0
edge_size_std_mean: 0.02807221164244637
```

Flat-hole efficiency evidence:

```text
sample: sample_000025
status: SUCCESS
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

## Active Task

`T-818_SCALE_ENTITY_DATA_AND_SEGMENTATION_GENERALIZATION`

Why:

- The compact end-to-end AI meshing tool now works on 8 held-out samples with real ANSA.
- T-817 fixed the most visible uniform fine-mesh collapse for the simple flat-hole case.
- The next bottleneck is broader generalization, not another fallback or benchmark wrapper.
- Edge segmentation still has weak rare-class coverage, especially slot/free/outer
  distinctions in mixed flat features.

## Known Gaps

1. The proof is compact; it is not yet production-scale generalization.
2. Face size controls remain optional; edge controls are the required path.
3. Rare edge classes still need more data and stronger validation.
4. Some semantic labels for slot/cutout side edges are still imperfect, although the
   efficiency gate no longer lets those labels corrupt far-field metrics.
5. The system assumes clean constant-thickness sheet-metal CAD; defeaturing remains out of scope.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
