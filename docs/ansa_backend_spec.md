# ANSA Backend Spec

The ANSA backend adapter stages `assembly.json`, `mesh_recipe.json`, and
`ansa_batch_config.json`, then constructs an ANSA no-GUI command with
`-exec load_script:<script>;run_batch_mesh:<config>`.
