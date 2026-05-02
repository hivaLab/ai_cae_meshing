# Final Delivery Report

Generated at: 2026-05-02T11:13:10.172141+00:00

## Workflow Commands
- validate_all_repository_schemas
- cad kernel status
- python scripts/run_step_ingestion_regression.py --sample-count 5
- cdf generate --num-samples 1000 --refinement-synthetic
- cdf validate-dataset
- cdf build-graphs
- train-brep-assembly-net
- evaluate-brep-assembly-net --split test
- export-amg-model
- ansa backend status
- amg run-mesh --backend ANSA_BATCH
- amg validate-result --backend ANSA_BATCH

## Verification Commands
- `python -m pytest -vv --basetemp .\tmp_pytest_refinement_pipeline`: 77 passed
- `python scripts\run_full_delivery.py`: ANSA_SMOKE_PASSED
- `python scripts\run_ansa_regression.py --sample-count 10`: 10 passed / 0 failed
- `python scripts\run_real_dataset_ingestion.py --help`: passed

## Dataset
- CAD kernel: CadQuery/OCP(OpenCascade)
- AP242 B-Rep export available: True
- Dataset ID: LGE_SYNTH_CAE_MESH_V001
- Dataset backend: SYNTHETIC_ORACLE
- Accepted samples: 1000
- Rejected samples: 142
- Total retained samples: 1142
- Splits: train 800 / val 100 / test 100
- Acceptance rate: 0.8757
- Dataset validation passed: True
- Topology families: 36
- Unique graph node shapes: 20
- Mesh-size label coverage: 1.000000
- Rejected sample ratio: 0.124343
- STEP AP242 B-Rep failures: 0
- STEP feature-bearing validation: enforced for synthetic samples
- Graph artifact validation passed: True
- graph.pt files: 1142
- brep_graph.json files: 1142
- assembly_graph.json files: 1142

## STEP Ingestion Regression
- Golden/external AP242 B-Rep samples: 5
- CAD dir: None
- Passed: 5
- Failed: 0
- Technical fixture validation passed: True
- Production validation accepted: False
- Limitation: Golden assemblies are locally generated AP242 B-Rep STEP fixtures; no external OEM STEP files were supplied.

## Model
- Model type: hetero_brep_assembly_net
- Model path: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\artifacts\models\brep_assembly_net_v001\model.pt
- Exported model path: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\artifacts\models\amg_deployment_model.pt
- Hidden dim: 32
- Message passing layers: 2
- Edge relation types: 16
- Train MAE: 0.272247
- Val MAE: 0.279360
- Test MAE: 0.277390
- Test RMSE: 0.353050
- Size MAE percent: 0.078555
- Refinement size MAE percent: 0.078555
- Face size MAE percent: 0.081933
- Edge size MAE percent: 0.077357
- Contact size MAE percent: 0.073505
- Feature refinement class accuracy: 0.960526
- PartStrategy macro F1: 1.000000
- FaceSemantic mean IoU: 1.000000
- EdgeSemantic macro F1: 0.500000
- Connection recall: 1.000000
- Failure risk recall: 1.000000
- Repair top-1 accuracy: 0.673175

## AMG Production Result
- Test sample: sample_001028
- Result package validation passed: True
- Production backend: ANSA_BATCH
- BDF parse success: True
- Missing properties: 0
- Missing materials: 0
- Shell elements: 125910
- Solid elements: 0
- Connectors: 8

## ANSA Backend
- Available: True
- Executable: C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
- Fallback enabled: False
- Execution probe attempted: True
- Execution probe passed: True
- Batch Meshing Manager invoked: True
- Batch Meshing Manager note: ANSA batchmesh sessions applied AI mesh recipe parameters per part and ran Batch Mesh Manager
- ANSA import counts: {'ANSAPART': 11, 'CBUSH': 0, 'CONM2': 0, 'FACE': 188, 'GRID': 0, 'MAT1': 1, 'PBUSH': 0, 'PSHELL': 13, 'PSOLID': 0, 'RBE2': 0, 'RBE3': 0, 'SHELL': 0, 'SOLID': 0, '__ELEMENTS__': 0}
- ANSA batch counts: {'ANSAPART': 11, 'CBUSH': 8, 'CONM2': 0, 'FACE': 188, 'GRID': 125485, 'MAT1': 4, 'PBUSH': 1, 'PSHELL': 13, 'PSOLID': 0, 'RBE2': 0, 'RBE3': 0, 'SHELL': 125910, 'SOLID': 0, '__ELEMENTS__': 125918}
- AI recipe batch sessions: 6
- Per-part size controls planned: 11
- Refinement zones planned: 206
- Required refinement zones planned: 197
- Parts with refinement zones: 11
- BMM refinement/size-control sessions applied: 6
- Materials written to deck: 4
- PSHELL properties updated: 6
- Solver-deck element fallback enabled: False
- Native CTETRA solids generated: 0
- Native CBUSH connectors generated: 8
- Native CONM2 masses generated: 0
- BDF traceability passed: True
- BDF traceability mapped parts: 11
- ANSA quality repair status: passed_no_repair_required
- ANSA QA repair loop records: 3

## ANSA Production Regression
- Command: `python scripts/run_ansa_regression.py --sample-count 10`
- Regression report: `ANSA_REGRESSION_REPORT.md`
- Sample count: 10
- Passed samples: 10
- Failed samples: 0
- Native CTETRA total: 3591694 / expected 7
- Native CBUSH total: 84 / expected 84
- Native CONM2 total: 6 / expected 6
- Total runtime seconds: 1253.702
- Synthetic regression acceptance: SYNTHETIC_ANSA_REGRESSION_ACCEPTED

## Known Limitations
- The 1,000 accepted samples plus retained rejected samples are deterministic refinement synthetic bootstrap data and are not evidence of general CAD production performance.
- Synthetic-oracle BDF artifacts are excluded from claims of engineer-approved high-quality training mesh ground truth.
- The built-in STEP ingestion regression uses local feature-bearing golden fixtures unless --cad-dir is supplied; fixture success is not real CAD validation.
- ANSA_BATCH is the only production AMG backend; no local procedural fallback is used for production meshing.
- LG/OEM production validation requires supplied CAD/Mesh pairs and acceptance metadata.

## Truthful Status
- Refinement synthetic bootstrap status: REFINEMENT_SYNTHETIC_BOOTSTRAP_ACCEPTED
- LG production validation status: LG_PRODUCTION_NOT_VALIDATED
- Real supervised dataset status: REAL_SUPERVISED_DATASET_NOT_AVAILABLE

## Final Acceptance Status

SYNTHETIC_ANSA_REGRESSION_ACCEPTED
