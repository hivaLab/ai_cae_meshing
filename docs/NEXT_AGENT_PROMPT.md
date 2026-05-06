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

Latest regression:

```powershell
python -m pytest
```

```text
69 passed
```

T-812 real evidence:

```text
dataset: runs\t812_diverse_entity_validation\dataset
profile: sm_entity_v2_diverse_quality
sample count: 32
train/test split: 24/8
size sweep: 32 attempted, 17 completed, 3 failed, 12 blocked
hard_fail rows: 18
near_fail rows: 18
quality rows: 260 total, 248 metric_available
```

Held-out AI gates:

```text
flat sample: sample_000025, SM_FLAT_PANEL
status: SUCCESS
edge size stats: count=10, min/mean/max/std=0.5/0.5899280985082083/0.625/0.04901566409509156
h_min edge fraction: 0.2
max boundary size error: 0.004648606178533798
BDF bytes: 9528865

bent sample: sample_000032, SM_HAT_CHANNEL
status: SUCCESS
edge size stats: count=24, min/mean/max/std=0.5/0.5449059218846366/0.625/0.05722437956992055
h_min edge fraction: 0.5
max boundary size error: 0.008064516129032473
BDF bytes: 20326149
```

Important caveat:

T-812 proves non-h_min AI size fields can pass real ANSA on one flat and one bent
held-out sample. It does not prove broad generalization. Quality-aware size-field
training used only 5 samples with usable evidence because flat slot cases blocked during
entity matching.

## Next Task

Implement:

```text
T-813_ENTITY_MATCHING_AND_QUALITY_EVIDENCE_COVERAGE
```

## Required Work

1. Diagnose `entity_matching_failed` for flat slot sweep samples:
   - `sample_000002`
   - `sample_000010`
   - `sample_000018`
2. Compare CDF and ANSA descriptors for failed slot cases and identify whether ambiguity
   comes from duplicate arcs, line endpoints, loop role, or descriptor tolerance.
3. Harden descriptor matching without weakening fail-closed behavior.
4. Re-run `local_quality_v1` sweep on the previously blocked flat slot samples.
5. Re-train size-field with `--prefer-quality-evidence`.
6. Confirm trained sample count increases and held-out AI gates still pass with nonzero
   target-size variance.

## Acceptance Direction

T-813 should be `DONE` only if:

- flat slot sweep no longer blocks with `entity_matching_failed`;
- quality-aware training uses substantially more than 5 samples;
- no ambiguous entity match is silently accepted;
- real ANSA reports, BDFs, and entity-local metrics remain required for counted success;
- graph arrays still contain no target, quality, label, or action leakage.

If matching remains ambiguous, keep T-813 `IN_PROGRESS` or `BLOCKED` and record the exact
CDF/ANSA descriptor mismatch rather than widening tolerance until it passes.
