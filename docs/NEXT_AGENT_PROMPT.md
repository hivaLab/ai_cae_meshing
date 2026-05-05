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
- T-701 through T-708 are complete with real ANSA evidence.
- Active task: T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA.
- Verified ANSA executable:
  C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Latest regression:
- python -m pytest
- Result: 229 passed, 2 skipped in 10.54s.

Recent T-708 real gate evidence:
1. Dataset validation:
   python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
   Result: SUCCESS, accepted_count=40, error_count=0.

2. Quality exploration:
   python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, baseline_count=40, evaluated_count=120, blocked_count=0, passed_count=84, near_fail_count=40, failed_count=36, quality_score_variance=2814384.4276997964.

3. Quality ranker training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --out runs\t708_quality_exploration_smoke\training_quality_metricfix2 --epochs 5 --batch-size 32 --seed 708
   Result: SUCCESS, validation_pairwise_accuracy=0.6666666666666666.

4. Quality benchmark:
   python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
   Result: SUCCESS.

Important T-708 evidence:
- quality benchmark: runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
- action_entropy_bits=2.272088893287269
- feature_type_entropy_bits=2.28558992945765
- control_value_variance=28.23013372004848
- passed_count=84
- near_fail_count=76 in benchmark evidence, including scored failed records
- failed_count=36
- blocked_count=0
- same_geometry_quality_delta_mean=1671.256000525
- same_geometry_meaningful_delta_count=40
- validation_pairwise_accuracy=0.6666666666666666

What changed in T-708:
- cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py now binds manifest controls to real ANSA API paths instead of only recording them.
- cdf_ansa_oracle.py passes full feature records into those control bindings.
- ANSA statistics parsing now reads the Session-Parts quality table and avoids confusing element-count TOTAL headers with violation totals.
- Accepted but margin-poor meshes are recorded as NEAR_FAIL.
- Hard-failed ANSA records with num_hard_failed_elements > 0 become FAILED labels even when continuous quality metrics are unavailable.

Immediate next task:
- T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA.

Closed implementation plan for T-709:
1. Re-read AMG.md, CDF.md, ANSA_INTEGRATION.md, STATUS.md, and TASKS.md sections about quality-aware learning, manifest controls, and real ANSA validation.
2. Add an AMG-side recommendation module that imports no cad_dataset_factory code and reads only file contracts:
   - dataset samples
   - graph/brep_graph.npz
   - graph/graph_schema.json
   - labels/amg_manifest.json
   - quality exploration records
   - quality ranker checkpoint/metrics
3. For held-out accepted samples, construct candidate manifests by perturbing controls in the same allowed space as T-708 or by reusing stored perturbation manifests when evaluating the same geometry.
4. Score candidate manifests with the T-708 quality ranker and select the predicted best lower-is-better control manifest.
5. Write schema-valid predicted AMG_MANIFEST_SM_V1 files. Do not copy label actions or controls as the prediction source except for structural fields required by the manifest contract.
6. Run real ANSA for:
   - baseline accepted manifest
   - recommended manifest
   - optional naive coarse/fine control baseline
7. Produce per-sample comparison reports and an aggregate recommendation benchmark:
   - baseline score
   - recommended score
   - naive score if available
   - improvement delta
   - improvement rate
   - real ANSA failure histogram
   - non-empty BDF evidence paths
8. T-709 is DONE only if the recommender improves lower-is-better real ANSA quality score over baseline for a meaningful fraction of attempted held-out samples, or it remains IN_PROGRESS with exact failure evidence.

Do not count any of these as success:
- mock ANSA
- placeholder mesh
- controlled failure report
- unavailable ANSA
- deterministic fallback manifest replacing model recommendation
- synthetic graph target columns
- reference_midsurface.step as model input
- geometry-level variance without same-geometry comparison

Suggested real smoke commands after implementation:
1. python -m pytest
2. python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\recommendation_metricfix2 --limit 10 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
3. python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t708_quality_exploration_smoke\recommendation_metricfix2 --out runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix2.json

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real recommendation gate commands/results
5. whether T-709 is DONE, IN_PROGRESS, or BLOCKED
6. next recommended task
7. blockers or risks
```
