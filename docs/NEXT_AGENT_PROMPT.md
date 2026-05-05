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
- T-701 through T-712 are complete with real ANSA evidence.
- Active phase: P7_REAL_PIPELINE_COMPLETION.
- Active task: T-713_MIXED_FAMILY_FRESH_AI_CONTROL_PROPOSAL.
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
- Result: 252 passed, 2 skipped in 12.68s.

Latest real gate, T-712 mixed/family AI-only recommendation:
1. Dataset generation:
   python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t712_quality_family_generalization\dataset --count 42 --seed 712 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_quality_family_generalization_v1
   Result: SUCCESS, accepted_count=42, rejected_count=2.

2. Strict validation:
   python -m cad_dataset_factory.cdf.cli validate --dataset runs\t712_quality_family_generalization\dataset --require-ansa
   Result: SUCCESS, accepted_count=42, error_count=0.

3. Quality exploration:
   python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t712_quality_family_generalization\dataset --out runs\t712_quality_family_generalization\quality_exploration --perturbations-per-sample 4 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, baseline_count=42, evaluated_count=168, passed_count=164, near_fail_count=46, failed_count=0, blocked_count=0, quality_score_variance=8.990343582400554.

4. Quality training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t712_quality_family_generalization\dataset --quality-exploration runs\t712_quality_family_generalization\quality_exploration --out runs\t712_quality_family_generalization\training_quality --epochs 5 --batch-size 32 --seed 712
   Result: SUCCESS, example_count=210, validation_pairwise_accuracy=0.8978102189781022.

5. AI-only recommendation:
   python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t712_quality_family_generalization\dataset --quality-exploration runs\t712_quality_family_generalization\quality_exploration --training runs\t712_quality_family_generalization\training_quality --out runs\t712_quality_family_generalization\recommendation_ai_only --split test --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, attempted_count=14, valid_pair_count=14, selected_baseline_count=0, compare_baseline=false.

6. AI-only coverage benchmark:
   python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t712_quality_family_generalization\recommendation_ai_only --out runs\t712_quality_family_generalization\recommendation_ai_only_benchmark.json --ai-only --dataset runs\t712_quality_family_generalization\dataset --split test --required-part-classes SM_FLAT_PANEL,SM_SINGLE_FLANGE,SM_L_BRACKET,SM_U_CHANNEL,SM_HAT_CHANNEL --required-feature-types HOLE,SLOT,CUTOUT,BEND,FLANGE
   Result: SUCCESS, valid_mesh_count=14, selected_non_baseline_count=14, selected_baseline_count=0, all required coverage present.

Important retained evidence:
- dataset: runs\t712_quality_family_generalization\dataset
- quality exploration summary: runs\t712_quality_family_generalization\quality_exploration\quality_exploration_summary.json
- training metrics: runs\t712_quality_family_generalization\training_quality\quality_training_metrics.json
- quality ranker: runs\t712_quality_family_generalization\training_quality\quality_ranker_checkpoint.pt
- AI-only recommendation summary: runs\t712_quality_family_generalization\recommendation_ai_only\recommendation_summary.json
- AI-only benchmark: runs\t712_quality_family_generalization\recommendation_ai_only_benchmark.json

Immediate next task:
- T-713_MIXED_FAMILY_FRESH_AI_CONTROL_PROPOSAL.

Closed implementation plan for T-713:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about
   fresh candidate proposal, real ANSA quality evidence, and model inputs.
2. Use the T-712 dataset and quality ranker. Do not generate a new CDF dataset unless the
   retained T-712 artifacts are missing.
3. Run AMG fresh candidate generation on the T-712 test split, not on the old T-708 smoke set.
   Candidate selection must not read quality_score, status, reports, or mesh artifacts.
4. Evaluate fresh candidates with real ANSA and append evidence under a new T-713 output root.
5. Retrain the quality ranker with T-712 baseline evidence plus T-713 fresh evidence.
6. Run AI-only recommendation on the same T-712 mixed/family test split with compare_baseline=false.
7. Benchmark in AI-only mode with required part-class and feature-type coverage.
8. T-713 is DONE only if every counted recommendation is a non-baseline AI manifest with
   real ANSA execution report, real quality report, hard failed element count 0, and non-empty BDF.

Recommended output root:
- runs\t713_mixed_family_fresh_ai_control

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real gate commands/results
5. whether T-713 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
