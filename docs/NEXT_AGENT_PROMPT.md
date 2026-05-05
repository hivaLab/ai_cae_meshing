# NEXT_AGENT_PROMPT.md

This is the rolling handoff prompt for the next coding session. Update it at the end of every completed task together with `docs/STATUS.md` and `docs/TASKS.md`.

```text
You are implementing the AMG/CDF project from the repository documents.

First, read these files in order:
1. AGENT.md
2. STATUS.md
3. TASKS.md
4. CONTRACTS.md
5. ARCHITECTURE.md
6. TESTING.md
7. ANSA_INTEGRATION.md
8. AMG.md
9. CDF.md
10. DATASET.md

Current state:
- P0 through P6 are complete.
- T-701 through T-711 are complete with real ANSA evidence.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-712_AI_ONLY_MIXED_FAMILY_QUALITY_GENERALIZATION.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Critical rule:
- The project goal is AI-based ANSA-linked high-quality sheet-metal mesh automation.
- Baseline mesh generation is not part of the primary recommendation success path.
- Baseline comparison may be used only through explicit audit flags such as --compare-baseline.
- Do not count fallback, mock ANSA, placeholder mesh, controlled failure, unavailable ANSA,
  synthetic graph targets, or reference_midsurface.step model input as success.

Latest regression:
- python -m pytest
- Result: 246 passed, 2 skipped in 12.54s.

Latest real gate, T-711 AI-only recommendation:
1. Fresh candidate generation:
   python -m ai_mesh_generator.amg.recommendation.fresh --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t711_ai_candidate_quality_improvement\training_quality_v2 --out runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --split test --candidates-per-sample 8 --limit 6 --seed 711 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, sample_count=6, generated_count=48, evaluated_count=48, blocked_count=0.

2. Refreshed quality training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --extra-quality-evidence runs\t710_fresh_quality_loop\fresh_quality_exploration --extra-quality-evidence runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --out runs\t711_ai_candidate_quality_improvement\training_quality_v2_refreshed --epochs 5 --batch-size 32 --seed 711
   Result: SUCCESS, example_count=256, validation_pairwise_accuracy=0.6666666666666666.

3. AI-only recommendation, no baseline execution:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --training runs\t711_ai_candidate_quality_improvement\training_quality_v2_refreshed --out runs\t711_ai_candidate_quality_improvement\recommendation_v2 --split test --limit 6 --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, attempted_count=6, valid_pair_count=6, selected_baseline_count=0, compare_baseline=false.

4. AI-only benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t711_ai_candidate_quality_improvement\recommendation_v2 --out runs\t711_ai_candidate_quality_improvement\recommendation_ai_only_benchmark_v2.json --ai-only
   Result: SUCCESS, mode=AI_ONLY, valid_mesh_count=6, selected_non_baseline_count=6, selected_baseline_count=0, failure_reason_counts={}.

Important retained evidence:
- AI-only benchmark: runs\t711_ai_candidate_quality_improvement\recommendation_ai_only_benchmark_v2.json
- recommendation summary: runs\t711_ai_candidate_quality_improvement\recommendation_v2\recommendation_summary.json
- fresh evidence summary: runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2\quality_exploration_summary.json
- refreshed quality ranker: runs\t711_ai_candidate_quality_improvement\training_quality_v2_refreshed\quality_ranker_checkpoint.pt

Immediate next task:
- T-712_AI_ONLY_MIXED_FAMILY_QUALITY_GENERALIZATION.

Closed implementation plan for T-712:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about
   real ANSA quality evidence, candidate controls, and model inputs.
2. Build or reuse a mixed/family quality evidence set that includes HOLE, SLOT, CUTOUT,
   BEND, FLANGE and multiple sheet-metal families. If the retained T-707 artifacts are not
   available, generate a small new mixed/family quality set instead of claiming coverage.
3. Train the quality ranker by AMG file contract only. AMG code must not import CDF and
   graph inputs must not contain target action/control columns.
4. Run AI-only recommendation on a held-out mixed/family split with compare_baseline=false.
5. Benchmark in AI-only mode. T-712 is DONE only if every counted recommendation is a
   non-baseline AI manifest with real ANSA execution report, real quality report,
   hard failed element count 0, and non-empty BDF.
6. If any family or feature type lacks quality evidence or fails real ANSA validation,
   keep T-712 IN_PROGRESS or BLOCKED and record the exact family, feature type, sample id,
   report paths, and failure reason.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-712 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
