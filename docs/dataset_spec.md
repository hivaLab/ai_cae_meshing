# Dataset Spec

CDF writes deterministic accepted samples under `samples/<sample_id>/`, plus
`dataset_index.parquet`, `dataset_manifest.json`, and split files.

The built-in 1,000-sample CDF dataset is a synthetic bootstrap dataset. It is
valid for schema, graph, training-loop, and ANSA smoke-regression development,
but it is not a production validation dataset for LG/OEM air-conditioner CAD.

Real supervised production claims require paired CAD/Mesh submissions validated
by `ai_mesh_generator.input.training_submission.validate_training_submission_dir`.
Every CAD product/part must map to explicit mesh, connector, mass,
approved-exclude, or manual-review/failure. Silent CAD part omission is a
validation failure.
