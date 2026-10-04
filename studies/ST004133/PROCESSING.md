# ST004133

Converter accepted in run `20261004T172542Z_e55121` (finish(complete) on v1; all development checks ok).

- Task: `task.yaml` (SHA-256 69bf1ce2af1a17a5f4f3756bb48a2b9b232af50e0d924f75d5436b57745aa427)
- Model: gpt-6.1-sol, effort high
- Sandbox image: sha256:184accedaf7d6ffdd2a4fffa6c95e9f5180d9c3ea86b0c74c11a6004d8e92d14
- Harness commit: 63fa9326541092c48ec054a062775e403f0a00be-dirty

## Re-run without a model

Fetch the deposit with `onboard fetch ST004133` if `data/raw/ST004133/` is missing, then run `onboard rerun studies/ST004133`. It checks the input hashes, runs this converter and its tests in the recorded sandbox image, and compares the output hashes with `manifest.json`.
