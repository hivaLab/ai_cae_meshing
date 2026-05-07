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

Latest regression:

```powershell
python -m pytest
```

```text
72 passed
```

## Real Evidence To Preserve

Slot matching repair:

```text
dataset: runs\t812_diverse_entity_validation\dataset
fixed flat slot samples: sample_000002, sample_000010, sample_000018
per sample sweep: 4 attempted, 3 completed, 1 mesh-quality failed, 0 blocked
```

Quality-aware training:

```text
output: runs\t813_entity_matching_closure\size_field
sample_count: 24
trained_sample_count: 8
skipped_sample_count: 16
edge target count: 110
edge target min/mean/max/std: 0.7875 / 3.1177 / 8.0 / 2.1553 mm
h_min edge fraction: 0.0
learning_signal_status: SUCCESS
```

Full AI-to-ANSA workflow:

```text
workflow: runs\t816_entity_ai_meshing_gate_v2\workflow_report.json
attempted_count: 8
valid_mesh_count: 8
status: SUCCESS
families: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
num_hard_failed_elements: 0 for every sample
entity-local metrics: available for every controlled entity
BDF outputs: non-empty for every sample
```

Important caveat:

The compact tool now works end to end, but mesh efficiency and semantic quality are not
yet strong enough. Predicted edge sizes are still conservative:

```text
predicted edge size std min/mean on held-out samples: 0.000531993286870984 / 0.03425069807954155
max h_min edge fraction: 0.9615384615384616
edge segmentation training accuracy: about 0.70
face segmentation training accuracy: about 0.956
```

## Next Task

Implement:

```text
T-817_SEGMENTATION_AND_SIZE_EFFICIENCY_IMPROVEMENT
```

## Required Work

1. Improve edge segmentation fidelity.
   - Add class-balanced loss or weighted sampling for rare classes.
   - Report per-class edge confusion/F1, not only aggregate accuracy.
   - Specifically inspect why flat samples receive `BEND_EDGE` predictions.
2. Improve size-field efficiency.
   - Add an efficiency-aware training term or label-selection penalty using shell element
     count/BDF size and h-min fraction.
   - Keep hard-fail and local boundary error penalties dominant.
   - Do not let the model pass by setting almost every edge to `h_min`.
3. Increase usable quality evidence without broad sample-count expansion.
   - Run targeted sweeps on skipped train samples.
   - Preserve failed/near-fail evidence; do not hide it.
4. Re-run the primary workflow:
   - `amg-entity-size-field-gate`
   - same 8-sample test split
   - real ANSA required
5. Acceptance should require:
   - `valid_mesh_count == attempted_count`
   - zero hard failed elements
   - all entity-local metrics available
   - lower h-min fraction than T-816
   - higher edge-size variance than T-816
   - improved per-class edge segmentation metrics

If real ANSA still succeeds only through heavy over-refinement, keep T-817 `IN_PROGRESS`
and record exact sample-level size distributions and reports rather than claiming a
quality improvement.
