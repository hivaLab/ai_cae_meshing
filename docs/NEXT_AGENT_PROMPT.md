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
- T-701 through T-707 are complete.
- T-707 proved the closed generated-family real pipeline benchmark:
  - dataset: runs\t707_family_benchmark\dataset
  - training: runs\t707_family_benchmark\training
  - inference: runs\t707_family_benchmark\inference
  - benchmark report: runs\t707_family_benchmark\benchmark_report.json
- Latest full regression:
  python -m pytest -> 210 passed, 1 skipped in 9.88s.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

T-707 real evidence:
- CDF generation:
  python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t707_family_benchmark\dataset --count 240 --seed 707 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_family_expansion_v1
  -> SUCCESS, accepted_count=240, rejected_count=1
- CDF validation:
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\t707_family_benchmark\dataset --require-ansa
  -> SUCCESS, accepted_count=240, error_count=0
- AMG training:
  python -m ai_mesh_generator.amg.training.real --dataset runs\t707_family_benchmark\dataset --out runs\t707_family_benchmark\training --epochs 15 --batch-size 16 --seed 707
  -> SUCCESS, label_coverage_ratio=1.0, candidate_count=660, manifest_feature_count=660
- AMG inference:
  python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t707_family_benchmark\dataset --checkpoint runs\t707_family_benchmark\training\checkpoint.pt --out runs\t707_family_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
  -> SUCCESS, attempted_count=36, success_count=36, failed_count=0
- Benchmark report:
  python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t707_family_benchmark\dataset --training runs\t707_family_benchmark\training --inference runs\t707_family_benchmark\inference --out runs\t707_family_benchmark\benchmark_report.json --profile sm_family_expansion_v1
  -> SUCCESS

T-707 coverage:
- part_class histogram:
  SM_FLAT_PANEL=120
  SM_SINGLE_FLANGE=30
  SM_L_BRACKET=30
  SM_U_CHANNEL=30
  SM_HAT_CHANNEL=30
- feature_type histogram:
  HOLE=60
  SLOT=60
  CUTOUT=60
  BEND=240
  FLANGE=240
- splits:
  train=168
  val=36
  test=36
- after-retry VALID_MESH rate:
  SM_FLAT_PANEL=1.0
  SM_SINGLE_FLANGE=1.0
  SM_L_BRACKET=1.0
  SM_U_CHANNEL=1.0
  SM_HAT_CHANNEL=1.0
  overall=1.0

Important implementation notes:
- CDF profile `sm_family_expansion_v1` generates eight interleaved case types:
  flat_hole, flat_slot, flat_cutout, flat_combo, single_flange, l_bracket, u_channel, hat_channel.
- Each case contributes 30 accepted samples for a total accepted target of 240.
- The profile writes deterministic 70/15/15 splits: train=168, val=36, test=36.
- HAT channel truth now records four structural flange/sidewall patches so truth features match detected B-rep graph candidates.
- Bent family profile dimensions are intentionally distinct across SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, and SM_HAT_CHANNEL so graph-level part-class inference is not geometrically ambiguous.
- AMG benchmark reporting now computes per-part-class attempted/success/failure counts and per-family VALID_MESH rates.

Non-negotiable constraints:
- AMG source must not import `cad_dataset_factory`.
- Graph inputs must not contain `target_action_id` or target numeric control columns.
- `cad/reference_midsurface.step` must not be used as a model input.
- Mock ANSA, disabled ANSA, controlled failures, unavailable ANSA, placeholder meshes, deterministic rule fallback, skipped families, or synthetic graph targets must never count as real success.
- If AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or real ANSA output semantics conflict, stop and report BLOCKED instead of guessing.

Remaining limitation:
- T-707 proves a deterministic generated-family benchmark, not production-scale diversity or model selection.
- The current model family still needs explicit selection evidence across larger real datasets, multiple seeds/configurations, and harder held-out distributions.

Next task:
- T-708_PRODUCTION_SCALE_DATASET_AND_MODEL_SELECTION

Work only on T-708 scope:
- Scale from closed generated benchmarks to a production-scale real ANSA-accepted dataset.
- Compare at least two explicit AMG model/training configurations on the same real train/val/test split.
- Select the checkpoint by real validation/test evidence, not smoke tests, synthetic targets, or training loss alone.
- Preserve file-contract boundaries between CDF and AMG.
- Keep all CDF accepted samples fail-closed under real ANSA validation.
- Keep AMG inference success tied to real ANSA reports and non-empty real mesh artifacts.

Recommended T-708 execution plan:
1. Define a production-scale profile and acceptance budget.
   - Start with all T-707 validated families and feature types.
   - Use a larger accepted target than T-707, with explicit per-family/per-feature minimum counts.
   - Keep generation deterministic by seed and write the target plan to the dataset artifacts.
2. Generate the production-scale CDF dataset with real ANSA enabled.
   - Run `cdf generate --require-ansa` with the verified ANSA executable.
   - Run `cdf validate --require-ansa`.
   - If any family/feature has low acceptance, analyze rejection histograms before changing generation logic.
3. Add model-selection training runs.
   - Train at least two named configurations, for example:
     `mlp_baseline_v1` and `mlp_wider_v1` or another explicit configuration supported by the current code.
   - Save each run under a separate output directory with `training_config.json`, `metrics.json`, and `checkpoint.pt`.
   - Record sample counts, label coverage, per-head losses, and validation loss curves.
4. Run real ANSA inference for each checkpoint on the same held-out test split.
   - Use `amg-infer-real --split test`.
   - Reject model/type/action mismatches fail-closed.
   - Count only real ANSA quality-passing meshes as `VALID_MESH`.
5. Build a model-selection report.
   - Include dataset coverage, training metrics, inference success rates, per-family rates, failure histograms, and selected checkpoint rationale.
   - Select the best checkpoint using real ANSA validation/test evidence.
6. Update `STATUS.md`, `TASKS.md`, and `NEXT_AGENT_PROMPT.md`.

Acceptance for T-708:
- Production-scale dataset generation and strict validation complete with real ANSA reports and meshes.
- Required family and feature coverage are present in accepted samples and split files.
- At least two explicit model/training configurations complete without target leakage.
- Real ANSA inference runs on the same held-out test split for every compared checkpoint.
- The selected checkpoint has documented real mesh success evidence and per-family rates.
- `python -m pytest` passes.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. production dataset command/result and accepted coverage
5. training commands/results for every compared configuration
6. real inference commands/results and per-family mesh quality metrics
7. selected checkpoint and rationale
8. next recommended task
9. blockers or risks
```
