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
- T-701 through T-713 are complete with real ANSA evidence.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-714_USER_SCALED_QUALITY_ACTIVE_LEARNING_ROUND.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Critical rule:
- The project goal is AI-based ANSA-linked high-quality sheet-metal mesh automation.
- Baseline mesh generation is not part of the primary recommendation success path.
- Baseline/reference records may exist only as label-side evidence.
- Do not count fallback, mock ANSA, placeholder mesh, controlled failure, unavailable ANSA,
  synthetic graph targets, or reference_midsurface.step model input as success.

Latest regression:
- python -m pytest
- Result: 252 passed, 2 skipped in 11.06s.

Latest real gate, T-713 mixed/family fresh AI control proposal:
1. Fresh proposal:
   python -m ai_mesh_generator.amg.recommendation.fresh --dataset runs\t712_quality_family_generalization\dataset --quality-exploration runs\t712_quality_family_generalization\quality_exploration --training runs\t712_quality_family_generalization\training_quality --out runs\t713_mixed_family_fresh_ai_control\fresh_quality_exploration --split test --candidates-per-sample 8 --seed 713 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, sample_count=14, generated_count=112, evaluated_count=112, blocked_count=0, unique_candidate_hash_count=112, quality_score_variance=10.314708118915938.

2. Refreshed quality training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t712_quality_family_generalization\dataset --quality-exploration runs\t712_quality_family_generalization\quality_exploration --extra-quality-evidence runs\t713_mixed_family_fresh_ai_control\fresh_quality_exploration --out runs\t713_mixed_family_fresh_ai_control\training_refreshed --epochs 5 --batch-size 32 --seed 713
   Result: SUCCESS, example_count=322, validation_pairwise_accuracy=0.8978102189781022.

3. AI-only recommendation:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t712_quality_family_generalization\dataset --quality-exploration runs\t713_mixed_family_fresh_ai_control\fresh_quality_exploration --training runs\t713_mixed_family_fresh_ai_control\training_refreshed --out runs\t713_mixed_family_fresh_ai_control\recommendation_ai_only --split test --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, attempted_count=14, valid_pair_count=14, selected_non_baseline_count=14, selected_baseline_count=0, compare_baseline=false.

4. AI-only coverage benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t713_mixed_family_fresh_ai_control\recommendation_ai_only --out runs\t713_mixed_family_fresh_ai_control\recommendation_ai_only_benchmark.json --ai-only --dataset runs\t712_quality_family_generalization\dataset --split test --required-part-classes SM_FLAT_PANEL,SM_SINGLE_FLANGE,SM_L_BRACKET,SM_U_CHANNEL,SM_HAT_CHANNEL --required-feature-types HOLE,SLOT,CUTOUT,BEND,FLANGE
   Result: SUCCESS, valid_mesh_count=14, selected_non_baseline_count=14, selected_baseline_count=0, all required coverage present.

Important retained evidence:
- T-712 dataset: runs\t712_quality_family_generalization\dataset
- T-712 quality exploration: runs\t712_quality_family_generalization\quality_exploration
- T-713 fresh evidence: runs\t713_mixed_family_fresh_ai_control\fresh_quality_exploration
- T-713 refreshed training: runs\t713_mixed_family_fresh_ai_control\training_refreshed
- T-713 AI-only recommendation: runs\t713_mixed_family_fresh_ai_control\recommendation_ai_only
- T-713 AI-only benchmark: runs\t713_mixed_family_fresh_ai_control\recommendation_ai_only_benchmark.json

Immediate next task:
- T-714_USER_SCALED_QUALITY_ACTIVE_LEARNING_ROUND.

Closed implementation plan for T-714:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about
   active learning, fresh candidate proposal, real ANSA quality evidence, and model inputs.
2. Do not start with blind large dataset generation. Add a user-scaled driver or orchestration
   path that exposes sample count, candidate count, split/sample selection, and ANSA run limits.
3. Use the T-713 path as the real working baseline: fresh AI candidates, real ANSA evidence append,
   refreshed quality training, and AI-only recommendation.
4. Report coverage, candidate uniqueness, quality score variance, pass/near-fail/fail/blocked
   counts, ranker validation metrics, AI-only VALID_MESH rate, and failure histograms.
5. Keep baseline/reference records label-side only. Do not allow baseline mesh generation,
   deterministic fallback, mock, placeholder, controlled failure, unavailable ANSA, synthetic graph
   targets, or reference_midsurface.step model input to count as success.
6. T-714 is DONE only if the user-scaled loop runs end-to-end at the configured budget and produces
   real ANSA evidence showing useful diversity and AI-only non-baseline VALID_MESH reliability.

Recommended output root:
- runs\t714_user_scaled_quality_active_learning

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-714 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
