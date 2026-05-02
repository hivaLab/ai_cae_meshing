# Input Package Spec

AMG accepts `LGE_CAE_MESH_JOB.zip` containing `geometry/assembly.step` and
metadata files under `metadata/`. The package is validated by
`schemas/input_package.schema.json`.

Production AMG execution uses `ANSA_BATCH`. Synthetic/local oracle meshing is
not a selectable production backend.

## Real Training Submission

Real CAD/Mesh pair collection uses a simpler source layout before it is converted
into AMG packages:

```text
sample_id/
  cad/raw.step
  ansa/final.ansa
  metadata/acceptance.csv
  metadata/quality_criteria.yaml
  solver/final.bdf
  reports/ansa_quality_report.*
```

Only the first four files are required. `solver/final.bdf` and ANSA quality
reports may be exported by the pipeline when ANSA is available.

`acceptance.csv` columns:

```text
sample_id,acceptance_status,reviewer,review_date,use_for_training,reject_reason,notes
```

Allowed `acceptance_status` values are `accepted`, `rejected`,
`needs_manual_review`, and `unknown`. Only `accepted` rows are positive
supervised labels.
