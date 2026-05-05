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
- T-701 through T-710 are complete with real ANSA evidence.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-711_RISK_AWARE_RECOMMENDATION_GUARDRAILS.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Latest regression:
- python -m pytest
- Result: 238 passed, 2 skipped in 11.11s.

Latest real active-learning gate:
1. Fresh candidate proposal:
   python -m ai_mesh_generator.amg.recommendation.fresh --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t710_fresh_quality_loop\fresh_quality_exploration --split test --candidates-per-sample 8 --limit 6 --seed 710 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, sample_count=6, generated_count=48, evaluated_count=48, blocked_count=0, unique_candidate_hash_count=48, quality_score_variance=2048357.424587557.

2. Refreshed quality training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --extra-quality-evidence runs\t710_fresh_quality_loop\fresh_quality_exploration --out runs\t710_fresh_quality_loop\training_refreshed --epochs 5 --batch-size 32 --seed 710
   Result: SUCCESS, example_count=208, validation_pairwise_accuracy=0.6666666666666666.

3. Refreshed recommendation:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t710_fresh_quality_loop\training_refreshed --out runs\t710_fresh_quality_loop\recommendation_refreshed --split test --limit 6 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, attempted_count=6, valid_pair_count=6, improved_count=5, improvement_rate=0.8333333333333334, median_improvement_delta=0.7116335000000036, selected_non_baseline_count=6.

4. Refreshed benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t710_fresh_quality_loop\recommendation_refreshed --out runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json --baseline runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
   Result: SUCCESS, improvement_rate_delta=0.0, median_improvement_delta_delta=0.3155714999999981.

Important T-710 evidence:
- fresh summary: runs\t710_fresh_quality_loop\fresh_quality_exploration\quality_exploration_summary.json
- refreshed training: runs\t710_fresh_quality_loop\training_refreshed
- refreshed recommendation: runs\t710_fresh_quality_loop\recommendation_refreshed
- refreshed benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json
- T-709 improvement_rate was preserved at 0.8333333333333334.
- median_improvement_delta improved from 0.39606200000000547 to 0.7116335000000036.
- selected_non_baseline_count increased from 5 to 6.
- No fresh candidate was counted from mock, placeholder, unavailable ANSA, controlled failure, or missing BDF.

Important remaining risk:
- sample_000036 regressed by -9.106281 in the refreshed recommendation gate.
- mean_improvement_delta is negative despite benchmark success.
- The next task must address downside risk, not simply increase sample count.

What changed in T-710:
- Added AMG-only fresh proposal module:
  ai_mesh_generator/amg/recommendation/fresh.py
- Added console script:
  amg-propose-quality
- Extended quality training to read --extra-quality-evidence roots.
- Extended recommendation benchmark to compare against a baseline benchmark.
- Added tests for fresh candidate determinism, schema validity, source boundaries, appended evidence, and baseline comparison.

Immediate next task:
- T-711_RISK_AWARE_RECOMMENDATION_GUARDRAILS.

Closed implementation plan for T-711:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about quality scoring, recommendation, and real ANSA validation.
2. Keep these baselines immutable:
   - T-709 benchmark: runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
   - T-710 benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json
3. Add downside-risk metrics to recommendation summary and benchmark:
   - worst_improvement_delta
   - severe_regression_count
   - lower_tail_delta_p10
   - lower_tail_delta_p25
4. Add configurable risk thresholds:
   - default severe regression threshold: improvement_delta < -1.0
   - default max severe_regression_count: 0
5. Add a risk-aware selection mode to recommendation:
   - Use ranker score for primary ranking.
   - Reject candidates whose predicted score is close to baseline but whose controls are high-risk outliers.
   - Allow explicit baseline fallback only when recorded as status=RISK_FALLBACK, not hidden success.
6. Re-run real ANSA on the same T-710 test sample set.
7. T-711 is DONE only if:
   - improvement_rate >= 0.8333333333333334
   - median_improvement_delta >= 0.7116335000000036
   - severe_regression_count=0
   - all counted successes have real ANSA reports and non-empty BDF outputs.

Do not count any of these as success:
- mock ANSA
- placeholder mesh
- controlled failure report
- unavailable ANSA
- deterministic fallback that is not recorded as a risk decision
- synthetic graph target columns
- reference_midsurface.step as model input
- hiding or deleting severe regression samples

Suggested first commands:
1. python -m pytest
2. Inspect T-710 regression sample:
   Get-Content runs\t710_fresh_quality_loop\recommendation_refreshed\samples\sample_000036\recommendation_report.json
3. Implement risk metrics and risk-aware selection.
4. Re-run the real recommendation/benchmark gate with the verified ANSA executable.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-711 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
