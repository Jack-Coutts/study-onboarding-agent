# ST000001

Converter accepted in run `20261004T161527Z_1c970b` (finish(complete) on v1; all development checks ok).

- Task: `task.yaml` (SHA-256 759f8a9857cfcafc256d8306cc3a688180378c890bf20b72907834efd93554bf)
- Model: gpt-6.1-sol, effort high
- Sandbox image: sha256:184accedaf7d6ffdd2a4fffa6c95e9f5180d9c3ea86b0c74c11a6004d8e92d14
- Harness commit: ed1df7e6662c44a25c62bce23144f8522a831ff7-dirty

## Re-run without a model

Fetch the deposit with `onboard fetch ST000001` if `data/raw/ST000001/` is missing, then run `onboard rerun studies/ST000001`. It checks the input hashes, runs this converter and its tests in the recorded sandbox image, and compares the output hashes with `manifest.json`.
