# Next Agent Prompt

## Current Direction

The primary path is fixed:

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

Latest regression:

```powershell
python -m pytest
```

```text
66 passed
```

T-811 real AI gate evidence:

```text
dataset: runs\t811_ai_size_field_gate\dataset
held-out sample: sample_000016
train split samples: 15
part prediction: SM_HAT_CHANNEL, confidence 0.48
AI size field: runs\t811_ai_size_field_gate\inference\sample_000016\amg_size_field_ai.json
AI context: runs\t811_ai_size_field_gate\inference\sample_000016\ai_size_field_context.json
ANSA eval: runs\t811_ai_size_field_gate\ansa_eval\sample_000016
gate report: runs\t811_ai_size_field_gate\ai_size_field_gate_report.json
status: SUCCESS
BDF bytes: 34354036
edge match count: 24
entity rows: 24
metric_available rows: 24
hard_fail rows: 0
max boundary size error: 0.0005120789403909587
```

Important caveat:

The first AI gate succeeded by predicting the lower bound `0.5 mm` for every controlled
edge. That proves the AI-to-ANSA path is real, but it is over-refined and not yet an
efficient high-quality meshing strategy.

## Next Task

Implement:

```text
T-812_DIVERSE_ENTITY_DATASET_AND_MODEL_VALIDATION
```

## Required Work

1. Generate a compact but more informative dataset with varied part families and feature
   cases.
2. Add size-field label variation and real ANSA evaluations that include:
   - pass
   - near-fail
   - fail
   - over-refined but valid cases
3. Train the direct size-field model on this evidence.
4. Run AI inference on held-out samples.
5. Require real ANSA validation for every counted success.
6. Report not only `VALID_MESH`, but also efficiency:
   - BDF size
   - shell element count
   - mean/max boundary size error
   - target size distribution
   - over-refinement rate

## Acceptance Direction

T-812 should not be marked done merely because meshes pass. It must show that the model
learns nontrivial size distributions instead of always choosing `h_min`.

Minimum success evidence:

- at least one held-out flat sample and one bent-family sample
- all counted samples use AI-predicted size fields
- real execution/quality/entity-local reports are accepted
- no mock, placeholder, baseline, label substitution, or fabricated metric
- predicted edge target sizes have nonzero variance
- accepted meshes are not all generated at `h_min`
