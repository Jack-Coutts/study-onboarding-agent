# ST002977

Converter accepted in run `20261004T173329Z_2ded90` (finish(complete) on v1; all development checks ok).

- Task: `task.yaml` (SHA-256 73efb6cdbe6287d38dda6e9a72b2867defb6bb7e1963dcd58ed685e10829ab99)
- Model: gpt-6.1-sol, effort high
- Sandbox image: sha256:184accedaf7d6ffdd2a4fffa6c95e9f5180d9c3ea86b0c74c11a6004d8e92d14
- Harness commit: 63fa9326541092c48ec054a062775e403f0a00be-dirty

## Re-run without a model

Fetch the deposit with `onboard fetch ST002977` if `data/raw/ST002977/` is missing, then run `onboard rerun studies/ST002977`. It checks the input hashes, runs this converter and its tests in the recorded sandbox image, and compares the output hashes with `manifest.json`.
