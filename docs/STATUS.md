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

`T-819_BALANCED_ENTITY_SIZE_FIELD_REAL_GATE` is complete.

What changed:

- Added `size_train` and `size_test` splits to the T-818 balanced entity dataset.
- Ran real ANSA `local_efficiency_v1` sweeps on the size train split.
- Trained the part classifier, segmentation model, and direct size-field GNN from the
  purpose-specific splits.
- Updated the end-to-end workflow so part/segmentation training can use their own splits
  while size-field learning uses quality evidence from `size_train`.
- Added geometry safety projection for round/arc edges so hole curvature resolution is
  preserved even when predicted segmentation is imperfect.

Regression:

```powershell
python -m pytest
```

Result:

```text
75 passed
```

## T-819 Real Evidence

Dataset:

```text
runs/t818_learning_balanced_dataset/dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 112
part split: part_train=84, part_test=28
segmentation split: segmentation_train=84, segmentation_test=28
size split: size_train=26, size_test=8
```

Size sweep:

```text
attempted_count: 130
completed_count: 84
failed_count: 46
blocked_count: 0
samples with quality evidence: 26/26
```

Workflow:

```text
runs/t819_balanced_size_field_gate/workflow_v3/workflow_report.json
status: SUCCESS
attempted_count: 8
valid_mesh_count: 8
success_count: 8
status_counts: SUCCESS=8
h_min_edge_fraction_max: 0.0
edge_size_std_mean: 0.3092246581205486
```

Model metrics in workflow:

```text
part_test accuracy: 1.0
segmentation_test edge accuracy: 0.8769771528998243
size-field trained samples: 26/26
size-field target std: 3.0309552440652308 mm
size-field target h-min fraction: 0.03773584905660377
```

## Active Task

`T-820_BALANCED_PROFILE_GENERALIZATION_AND_FACE_CONTROL_PILOT`

Why:

- T-819 proves the balanced entity dataset can drive the real AI size-field ANSA gate.
- The next bottleneck is broader generalization and optional face-size controls, not
  another fallback or baseline route.
- OUTER_BOUNDARY remains the weakest edge class, and the current gate is still compact.

## Known Gaps

1. The proof is compact; it is not yet production-scale generalization.
2. Face size controls remain optional; edge controls are the required path.
3. OUTER_BOUNDARY remains the weakest edge class and needs more targeted geometry or
   model work.
4. Face size controls remain optional and have not yet been proven in the real ANSA gate.
5. The system assumes clean constant-thickness sheet-metal CAD; defeaturing remains out of scope.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
