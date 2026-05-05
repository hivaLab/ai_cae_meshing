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
- T-711 is IN_PROGRESS.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-711_AI_CANDIDATE_QUALITY_IMPROVEMENT.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Important correction:
- Baseline fallback is forbidden. The project goal is AI-based ANSA-linked high-quality mesh automation.
- Risk-aware recommendation must not select baseline as a successful recommendation.
- If no non-baseline AI candidate passes the risk gate, the sample must fail visibly with
  no_ai_candidate_passed_risk_gate.

Latest regression:
- python -m pytest
- Result after candidate-improvement code pass: 244 passed, 2 skipped in 12.23s.
- Targeted correction check:
  python -m pytest tests\test_amg_fresh_quality_proposal.py tests\test_amg_quality_candidate_diagnostics.py tests\test_amg_quality_training.py tests\test_cdf_ansa_internal_script_skeleton.py tests\test_amg_quality_recommendation.py
  Result: 24 passed in 2.99s.

Latest fail-closed real gate:
1. Risk-aware recommendation without baseline fallback:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t710_fresh_quality_loop\training_refreshed --out runs\t710_fresh_quality_loop\recommendation_risk_failclosed --split test --limit 6 --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: PARTIAL_FAILED, attempted_count=6, valid_pair_count=5, improved_count=5, improvement_rate=1.0 over valid AI pairs, median_improvement_delta=0.7940939999999973, severe_regression_count=0, selected_baseline_count=0, failure_reason_counts={no_ai_candidate_passed_risk_gate: 1}.

2. Benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t710_fresh_quality_loop\recommendation_risk_failclosed --out runs\t710_fresh_quality_loop\recommendation_benchmark_risk_failclosed.json --baseline runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json --min-improvement-rate 0.8333333333333334 --min-median-delta 0.7116335000000036 --severe-regression-threshold -1.0 --max-severe-regression-count 0
   Result: FAILED because all_pairs_valid=false and sample_000036 has no non-baseline AI candidate passing the risk gate.

Important evidence:
- recommendation summary: runs\t710_fresh_quality_loop\recommendation_risk_failclosed\recommendation_summary.json
- recommendation benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_risk_failclosed.json
- sample_000036 must not be treated as success by selecting baseline.
- Its evaluated fresh candidates in runs\t710_fresh_quality_loop\fresh_quality_exploration are all worse than baseline under the current quality score, so the actual problem is candidate/model quality.

What changed in the corrective pass:
- ai_mesh_generator/amg/recommendation/quality.py no longer falls back to baseline in risk-aware mode.
- The non-risk-aware recommendation path also treats baseline as comparison evidence only, never as the selected recommendation.
- Real recommendation now runs only the selected non-baseline AI manifest by default; baseline ANSA execution is available only with --compare-baseline for explicit audit/benchmark work.
- ai_mesh_generator/amg/benchmark/recommendation.py marks baseline recommendation as invalid for AI recommendation benchmark and reports sample failure codes directly.
- tests/test_amg_quality_recommendation.py now verifies fail-closed behavior instead of baseline fallback.
- ai_mesh_generator/amg/recommendation/fresh.py now generates non-baseline SUPPRESS candidates for small relief/drain features instead of forcing every suppressed feature into KEEP_REFINED.
- cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py binds suppression_max_diameter_scale into the real ANSA fill/suppression API path.
- ai_mesh_generator/amg/quality_features.py includes suppression_max_diameter_scale, so T-711 requires retraining the quality ranker before fresh proposal/recommendation.
- ai_mesh_generator/amg/diagnostics/quality_candidates.py adds an AMG-only candidate diagnostic CLI:
  python -m ai_mesh_generator.amg.diagnostics.quality_candidates --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --sample-id sample_000036 --out runs\t710_fresh_quality_loop\sample_000036_candidate_diagnostic.json

Immediate next task:
- Continue T-711 as T-711_AI_CANDIDATE_QUALITY_IMPROVEMENT.

Closed implementation plan:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about AI recommendation and real ANSA quality validation.
2. Because the quality feature vector changed, retrain the quality ranker before running fresh proposal:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --extra-quality-evidence runs\t710_fresh_quality_loop\fresh_quality_exploration --out runs\t711_ai_candidate_quality_improvement\training_quality_v2 --epochs 5 --batch-size 32 --seed 711
   Already run once as a sanity check: status=SUCCESS but validation_pairwise_accuracy=0.4. Treat this as evidence that ranker calibration/features need improvement before claiming T-711 success.
3. Generate and real-ANSA-evaluate fresh candidates with the improved suppression/control search:
   python -m ai_mesh_generator.amg.recommendation.fresh --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t711_ai_candidate_quality_improvement\training_quality_v2 --out runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --split test --candidates-per-sample 8 --limit 6 --seed 711 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
4. Retrain with the new T-711 fresh evidence:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --extra-quality-evidence runs\t710_fresh_quality_loop\fresh_quality_exploration --extra-quality-evidence runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --out runs\t711_ai_candidate_quality_improvement\training_quality_v2_refreshed --epochs 5 --batch-size 32 --seed 711
5. Re-run the held-out risk-aware recommendation gate without baseline execution:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t711_ai_candidate_quality_improvement\fresh_quality_exploration_v2 --training runs\t711_ai_candidate_quality_improvement\training_quality_v2_refreshed --out runs\t711_ai_candidate_quality_improvement\recommendation_v2 --split test --limit 6 --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
6. For explicit old-style comparison only, add --compare-baseline. Do not use this as the primary AI success claim.
7. Benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t711_ai_candidate_quality_improvement\recommendation_v2 --out runs\t711_ai_candidate_quality_improvement\recommendation_benchmark_v2.json --baseline runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json --min-improvement-rate 0.8333333333333334 --min-median-delta 0.7116335000000036 --severe-regression-threshold -1.0 --max-severe-regression-count 0
6. T-711 is DONE only if:
   - attempted_count=6,
   - valid_pair_count=6,
   - selected_baseline_count=0,
   - no_ai_candidate_passed_risk_gate=0,
   - severe_regression_count=0,
   - all counted recommendations are non-baseline AI manifests with real ANSA reports and non-empty BDF outputs.

Do not count any of these as success:
- baseline fallback recommendation
- mock ANSA
- placeholder mesh
- controlled failure report
- unavailable ANSA
- deterministic fallback disguised as AI
- synthetic graph target columns
- reference_midsurface.step as model input
- hiding or deleting failed samples

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-711 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
