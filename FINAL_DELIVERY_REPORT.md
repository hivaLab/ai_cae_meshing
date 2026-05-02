# Final Delivery Report

Generated at: 2026-05-02T09:22:20.080315+00:00

## Workflow Commands
- validate_all_repository_schemas
- cad kernel status
- python scripts/run_step_ingestion_regression.py --sample-count 5
- cdf generate --num-samples 1000 --feature-bearing-synthetic
- cdf validate-dataset
- cdf build-graphs
- train-brep-assembly-net
- evaluate-brep-assembly-net --split test
- export-amg-model
- ansa backend status
- amg run-mesh --backend ANSA_BATCH
- amg validate-result --backend ANSA_BATCH

## Dataset
- CAD kernel: CadQuery/OCP(OpenCascade)
- AP242 B-Rep export available: True
- Dataset ID: LGE_SYNTH_CAE_MESH_V001
- Dataset backend: SYNTHETIC_ORACLE
- Accepted samples: 1000
- Rejected samples: 0
- Splits: train 800 / val 100 / test 100
- Acceptance rate: 1.0000
- Dataset validation passed: True
- STEP AP242 B-Rep failures: 0
- STEP feature-bearing validation: enforced for synthetic samples
- Graph artifact validation passed: True
- graph.pt files: 1000
- brep_graph.json files: 1000
- assembly_graph.json files: 1000

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
- Train MAE: 0.476902
- Val MAE: 0.483272
- Test MAE: 0.488535
- Test RMSE: 0.573478
- Size MAE percent: 0.075003
- PartStrategy macro F1: 1.000000
- FaceSemantic mean IoU: 1.000000
- EdgeSemantic macro F1: 0.500000
- Connection recall: 1.000000
- Failure risk recall: 1.000000
- Repair top-1 accuracy: 0.639091

## AMG Production Result
- Test sample: sample_000900
- Result package validation passed: True
- Production backend: ANSA_BATCH
- BDF parse success: True
- Missing properties: 0
- Missing materials: 0
- Shell elements: 9424
- Solid elements: 45017
- Connectors: 8

## ANSA Backend
- Available: True
- Executable: C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
- Fallback enabled: False
- Execution probe attempted: True
- Execution probe passed: True
- Batch Meshing Manager invoked: True
- Batch Meshing Manager note: ANSA batchmesh sessions applied AI mesh recipe parameters per part and ran Batch Mesh Manager
- ANSA import counts: {'ANSAPART': 11, 'CBUSH': 0, 'CONM2': 0, 'FACE': 187, 'GRID': 0, 'MAT1': 1, 'PBUSH': 0, 'PSHELL': 15, 'PSOLID': 0, 'RBE2': 0, 'RBE3': 0, 'SHELL': 0, 'SOLID': 0, '__ELEMENTS__': 0}
- ANSA batch counts: {'ANSAPART': 22, 'CBUSH': 7, 'CONM2': 1, 'FACE': 189, 'GRID': 12522, 'MAT1': 15, 'PBUSH': 1, 'PSHELL': 15, 'PSOLID': 22, 'RBE2': 0, 'RBE3': 0, 'SHELL': 9424, 'SOLID': 36035, '__ELEMENTS__': 45467}
- AI recipe batch sessions: 7
- Per-part size fields planned: 11
- BMM size-field sessions applied: 7
- Materials written to deck: 4
- PSHELL properties updated: 7
- Solver-deck element fallback enabled: False
- Native CTETRA solids generated: 36035
- Native CBUSH connectors generated: 7
- Native CONM2 masses generated: 1
- BDF traceability passed: True
- BDF traceability mapped parts: 11
- ANSA quality repair status: passed_after_repair
- ANSA QA repair loop records: 4

## ANSA Production Regression
- Command: `python scripts/run_ansa_regression.py --sample-count 10`
- Regression report: `ANSA_REGRESSION_REPORT.md`
- Sample count: 10
- Passed samples: 10
- Failed samples: 0
- Native CTETRA total: 381188 / expected 10
- Native CBUSH total: 70 / expected 70
- Native CONM2 total: 10 / expected 10
- Total runtime seconds: 308.763
- Regression acceptance: ANSA_REGRESSION_ACCEPTED

## Known Limitations
- The 1,000-sample dataset is deterministic feature-bearing synthetic bootstrap data and is not evidence of LG/OEM production performance.
- The built-in STEP ingestion regression uses local feature-bearing golden fixtures unless --cad-dir is supplied; fixture success is not real CAD validation.
- ANSA_BATCH is the only production AMG backend; no local procedural fallback is used for production meshing.
- LG/OEM production validation requires supplied CAD/Mesh pairs and acceptance metadata.

## Truthful Status
- Feature synthetic bootstrap status: FEATURE_SYNTHETIC_BOOTSTRAP_ACCEPTED
- LG production validation status: LG_PRODUCTION_NOT_VALIDATED

## Final Acceptance Status

ANSA_REGRESSION_ACCEPTED
