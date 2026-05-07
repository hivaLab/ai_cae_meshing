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

`T-818_DIVERSITY_FIRST_ENTITY_LEARNING_DATASET` is complete.

What changed:

- Added CDF profile `sm_entity_v2_learning_balanced_v1`.
- Generated a compact 112-sample diversity-first dataset for part classification and
  face/edge segmentation.
- Added clean `OTHER` CAD examples so the sixth part-class output is trainable.
- Added purpose-specific splits: `part_train`, `part_test`, `segmentation_train`,
  and `segmentation_test`.
- Added `label_coverage_report.json` with per-split part, face, edge, and profile-case
  support.
- Added explicit `--eval-split` evaluation to part-classifier and segmentation training.
- Expanded the part-classifier input from raw part bbox/counts to CAD-native graph summary
  features so flat feature-rich plates and bent families are distinguishable.

Regression:

```powershell
python -m pytest
```

Result:

```text
73 passed
```

## T-818 Learning Evidence

Dataset:

```text
runs/t818_learning_balanced_dataset/dataset
profile: sm_entity_v2_learning_balanced_v1
sample_count: 112
part split: part_train=84, part_test=28
segmentation split: segmentation_train=84, segmentation_test=28
```

Part classifier:

```text
part_test accuracy: 1.0
part_test classes: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET,
  SM_U_CHANNEL, SM_HAT_CHANNEL, OTHER
```

Segmentation:

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

Reference comparison:

```text
T-817 held-out edge accuracy: 0.6832
T-818 segmentation_test edge accuracy: 0.8858
Previously weak classes SLOT_BOUNDARY, OUTER_BOUNDARY, FREE_EDGE, and
CUTOUT_BOUNDARY now have nonzero and improved F1.
```

## Active Task

`T-819_BALANCED_ENTITY_SIZE_FIELD_REAL_GATE`

Why:

- T-818 fixed the immediate part-class and segmentation dataset weakness.
- The next step is to connect this stronger dataset back into the real ANSA size-field
  gate.
- We need to verify that improved segmentation actually improves AI-predicted edge sizes
  and preserves the T-817 efficiency criteria under real ANSA.

## Known Gaps

1. The proof is compact; it is not yet production-scale generalization.
2. Face size controls remain optional; edge controls are the required path.
3. OUTER_BOUNDARY remains the weakest edge class and needs more targeted geometry or
   model work.
4. T-818 did not run a real ANSA size-field gate; it focused on learning data and
   classifier/segmentation accuracy.
5. The system assumes clean constant-thickness sheet-metal CAD; defeaturing remains out of scope.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
