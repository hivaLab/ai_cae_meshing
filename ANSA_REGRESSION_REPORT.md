# ANSA Regression Report

Generated at: 2026-05-02T11:34:14.621982+00:00
Dataset: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\CAE_MESH_DATASET_V001
Model: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\artifacts\models\amg_deployment_model.pt
Sample count: 10
Passed: 10
Failed: 0
Total runtime seconds: 1253.702
Native CTETRA total: 3591694 / expected 7
Native CBUSH total: 84 / expected 84
Native CONM2 total: 6 / expected 6
Acceptance: SYNTHETIC_ANSA_REGRESSION_ACCEPTED

## Sample Results

| sample_id | accepted | bdf | missing P/M/N | native CTE/CB/CM | expected S/C/M | BMM sessions | quality | threshold violations | runtime s | failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sample_001028 | True | True | 0/0/0 | 0/8/0 | 0/8/0 | 6 | passed_no_repair_required | 0 | 77.225 |  |
| sample_001029 | True | True | 0/0/0 | 442717/7/1 | 2/7/1 | 7 | passed_after_repair | 0 | 125.397 |  |
| sample_001030 | True | True | 0/0/0 | 0/8/0 | 0/8/0 | 8 | passed_no_repair_required | 0 | 43.675 |  |
| sample_001032 | True | True | 0/0/0 | 841201/10/1 | 1/10/1 | 9 | passed_after_repair | 0 | 219.832 |  |
| sample_001033 | True | True | 0/0/0 | 0/7/1 | 0/7/1 | 7 | passed_no_repair_required | 0 | 50.146 |  |
| sample_001034 | True | True | 0/0/0 | 0/9/0 | 0/9/0 | 6 | passed_no_repair_required | 0 | 76.66 |  |
| sample_001035 | True | True | 0/0/0 | 641607/8/1 | 2/8/1 | 7 | passed_after_repair | 0 | 174.153 |  |
| sample_001036 | True | True | 0/0/0 | 0/9/0 | 0/9/0 | 8 | passed_no_repair_required | 0 | 44.193 |  |
| sample_001037 | True | True | 0/0/0 | 768084/8/1 | 1/8/1 | 8 | passed_after_repair | 0 | 211.775 |  |
| sample_001038 | True | True | 0/0/0 | 898085/10/1 | 1/10/1 | 10 | passed_after_repair | 0 | 230.646 |  |

## Traceability

| sample_id | bdf traceability | mapped parts | failures |
| --- | --- | --- | --- |
| sample_001028 | True | 11 | 0 |
| sample_001029 | True | 12 | 0 |
| sample_001030 | True | 13 | 0 |
| sample_001032 | True | 15 | 0 |
| sample_001033 | True | 12 | 0 |
| sample_001034 | True | 12 | 0 |
| sample_001035 | True | 13 | 0 |
| sample_001036 | True | 14 | 0 |
| sample_001037 | True | 13 | 0 |
| sample_001038 | True | 16 | 0 |
