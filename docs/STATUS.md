# Project Status

## Current State

The active project is now a B-rep entity AI meshing tool. Feature-manifest,
recommendation/ranker, and baseline-selection paths are not active success paths.

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

`T-813` through `T-816` are complete.

What changed:

- Slot arc entity matching now uses endpoint-pair, radius, curve-plane, and length
  descriptors instead of unstable arc center matching.
- Flat slot sweep samples `sample_000002`, `sample_000010`, and `sample_000018` no
  longer block with `entity_matching_failed`.
- Quality-aware size-field training records target-size statistics and fails visibly
  when the target signal collapses.
- Added `amg-entity-size-field-gate`, the primary end-to-end runner.

Regression:

```powershell
python -m pytest
```

Result:

```text
72 passed
```

## Real ANSA Evidence

Slot sweep repair:

```text
dataset: runs/t812_diverse_entity_validation/dataset
samples repaired: sample_000002, sample_000010, sample_000018
per sample sweep: 4 attempted, 3 completed, 1 mesh-quality failed, 0 blocked
```

Quality-aware training after repair:

```text
output: runs/t813_entity_matching_closure/size_field
split: train
sample_count: 24
trained_sample_count: 8
skipped_sample_count: 16
edge target count: 110
edge target min/mean/max/std: 0.7875 / 3.1177 / 8.0 / 2.1553 mm
h_min edge fraction: 0.0
learning_signal_status: SUCCESS
```

Full held-out AI-to-ANSA gate:

```text
workflow: runs/t816_entity_ai_meshing_gate_v2/workflow_report.json
attempted_count: 8
valid_mesh_count: 8
status: SUCCESS
families: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
num_hard_failed_elements: 0 for every sample
entity-local metrics: available for every controlled entity
BDF outputs: non-empty for every sample
```

Learning signal in the final workflow:

```text
size-field trained samples: 8 / 24 train samples
target size std: 2.1553154324235733
target h_min fraction: 0.0
predicted edge size std min/mean on test split: 0.000531993286870984 / 0.03425069807954155
max predicted h_min edge fraction: 0.9615384615384616
```

## Active Task

`T-817_SEGMENTATION_AND_SIZE_EFFICIENCY_IMPROVEMENT`

Why:

- The first compact end-to-end AI meshing tool now works on the full 8-sample held-out
  split with real ANSA.
- The next bottleneck is no longer basic functionality; it is mesh efficiency and
  semantic fidelity.
- Edge segmentation train accuracy is only about `0.70`.
- Several held-out predictions are still heavily conservative near `h_min`, especially
  the flat combo case with `h_min_edge_fraction=0.9615`.

## Known Gaps

1. The model is compact and not yet production generalization evidence.
2. Size predictions pass ANSA but remain too conservative.
3. Edge segmentation confuses some flat boundaries with bend/internal classes.
4. Quality evidence coverage improved from 5 to 8 train samples, but 16 train samples
   are still skipped because their sweep evidence is incomplete or unusable.
5. Face controls remain optional; edge controls are the current required success path.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
