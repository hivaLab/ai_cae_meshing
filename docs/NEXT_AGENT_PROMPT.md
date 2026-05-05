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
- T-701 through T-709 are complete with real ANSA evidence.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-710_FRESH_QUALITY_CONTROL_PROPOSAL_AND_ACTIVE_LEARNING_LOOP.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Latest regression:
- python -m pytest
- Result: 234 passed, 2 skipped in 10.81s.

Latest real recommendation gate:
1. Quality recommendation:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\recommendation_metricfix4 --split test --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, attempted_count=6, valid_pair_count=6, improved_count=5, improvement_rate=0.8333333333333334, median_improvement_delta=0.39606200000000547, selected_non_baseline_count=5, failure_reason_counts={}.

2. Recommendation benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t708_quality_exploration_smoke\recommendation_metricfix4 --out runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
   Result: SUCCESS.

Important T-709 evidence:
- recommendation summary: runs\t708_quality_exploration_smoke\recommendation_metricfix4\recommendation_summary.json
- recommendation benchmark: runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
- all 6 paired samples have baseline and recommended real ANSA reports plus non-empty BDF outputs.
- improvement_rate=0.8333333333333334.
- median_improvement_delta=0.39606200000000547.
- selected_non_baseline_count=5.
- No mock, placeholder, unavailable ANSA, controlled failure, or missing mesh output counted as success.

What changed in T-709:
- Added AMG-side quality recommendation module:
  ai_mesh_generator/amg/recommendation/quality.py
- Added recommendation benchmark module:
  ai_mesh_generator/amg/benchmark/recommendation.py
- Added shared AMG quality feature-vector helper:
  ai_mesh_generator/amg/quality_features.py
- Updated AMG quality training to use the same vector helper as recommendation.
- Added console scripts:
  amg-recommend-quality
  amg-recommendation-benchmark
- Extended the real ANSA suppression/fill binding path so baseline and recommended manifests both produce real mesh artifacts.

Immediate next task:
- T-710_FRESH_QUALITY_CONTROL_PROPOSAL_AND_ACTIVE_LEARNING_LOOP.

Closed implementation plan for T-710:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about quality-aware learning, real ANSA validation, and manifest control bounds.
2. Keep the T-709 baseline immutable for comparison:
   - recommendation root: runs\t708_quality_exploration_smoke\recommendation_metricfix4
   - improvement_rate=0.8333333333333334
   - median_improvement_delta=0.39606200000000547
3. Add a fresh candidate proposal module that imports no cad_dataset_factory code and reads only AMG/CDF file contracts.
4. Generate fresh, schema-valid AMG_MANIFEST_SM_V1 candidate manifests from the trained ranker/model policy rather than selecting only from already evaluated T-708 perturbation manifests.
5. Candidate controls must respect:
   - h_min_mm <= target length <= h_max_mm
   - growth_rate_max bounds
   - positive integer washer rings, bend rows, and divisions
   - canonical feature/action compatibility
6. Candidate selection must not read quality_score, status, pass/fail labels, real ANSA reports, or mesh-quality evidence.
7. Execute fresh candidates with real ANSA and preserve pass, near-fail, fail, and blocked outcomes. Do not count mock, placeholder, unavailable ANSA, controlled failure, or missing/non-empty-invalid BDF as success.
8. Append fresh evidence to the quality-learning corpus without adding graph target columns or using reference_midsurface.step as model input.
9. Retrain or fine-tune the quality ranker on baseline + fresh evidence.
10. Re-run the recommendation benchmark on a held-out split and compare against T-709.

T-710 DONE criteria:
- Fresh candidate manifests are not copied from prior evaluated perturbation labels.
- Fresh candidate real ANSA executions produce valid evidence records.
- The refreshed model preserves or improves T-709 recommendation metrics:
  improvement_rate >= 0.8333333333333334 or justified statistical tie with higher control/candidate diversity.
  median_improvement_delta >= 0.39606200000000547 or justified statistical tie with higher control/candidate diversity.
- Candidate/control diversity increases relative to T-709.
- All success counts are backed by real ANSA reports and non-empty BDF meshes.

Do not count any of these as success:
- mock ANSA
- placeholder mesh
- controlled failure report
- unavailable ANSA
- deterministic fallback manifest replacing model recommendation
- synthetic graph target columns
- reference_midsurface.step as model input
- selecting from quality labels by reading quality_score/status

Suggested first commands:
1. python -m pytest
2. Inspect T-709 summary and benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t708_quality_exploration_smoke\recommendation_metricfix4 --out runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4_recheck.json
3. Implement fresh candidate proposal and active-learning append path.
4. Run a small real gate with the verified ANSA executable.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-710 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
