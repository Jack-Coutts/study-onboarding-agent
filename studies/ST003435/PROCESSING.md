# ST003435

Converter accepted in run `20261004T171606Z_05cd09` (finish(complete) on v1; all development checks ok).

- Task: `task.yaml` (SHA-256 6c1975d2cd2fc4650a9044766017614d9267ca8515c44cdb7f1a6daadc40687e)
- Model: gpt-6.1-sol, effort high
- Sandbox image: sha256:184accedaf7d6ffdd2a4fffa6c95e9f5180d9c3ea86b0c74c11a6004d8e92d14
- Harness commit: 63fa9326541092c48ec054a062775e403f0a00be-dirty

## Re-run without a model

Fetch the deposit with `onboard fetch ST003435` if `data/raw/ST003435/` is missing, then run `onboard rerun studies/ST003435`. It checks the input hashes, runs this converter and its tests in the recorded sandbox image, and compares the output hashes with `manifest.json`.
