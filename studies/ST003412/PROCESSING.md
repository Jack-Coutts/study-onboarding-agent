# ST003412

Converter accepted in run `20261004T163725Z_342b90` (finish(complete) on v1; all development checks ok).

- Task: `task.yaml` (SHA-256 99c7026d03ef35f8c598cf5ba2d6a1301bf344d37e5ad7c04bf54f57d15d6cb8)
- Model: gpt-6.1-sol, effort high
- Sandbox image: sha256:184accedaf7d6ffdd2a4fffa6c95e9f5180d9c3ea86b0c74c11a6004d8e92d14
- Harness commit: 514996f996a6101c920704b13d262f2af184c5af-dirty

## Re-run without a model

Fetch the deposit with `onboard fetch ST003412` if `data/raw/ST003412/` is missing, then run `onboard rerun studies/ST003412`. It checks the input hashes, runs this converter and its tests in the recorded sandbox image, and compares the output hashes with `manifest.json`.
