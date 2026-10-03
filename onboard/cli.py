"""The `onboard` command line (spec section 18)."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from onboard.config import DEFAULT_CONFIG, ROOT, load_config


def _fetch(args: argparse.Namespace) -> int:
    from onboard.fetch import fetch_study

    record = fetch_study(args.study_id)
    for entry in record["files"]:
        print(f"{entry['path']}: {entry['bytes']} bytes, sha256 {entry['sha256']}")
    print(f"recorded in data/SOURCES.json (licence: {record['licence']})")
    return 0


def _check_sandbox(args: argparse.Namespace) -> int:
    from onboard.sandbox import check_sandbox

    config = load_config(args.config)
    with tempfile.TemporaryDirectory() as tmp:
        passed, problems, digest = check_sandbox(config, args.build, Path(tmp))
    print(f"image {digest}")
    for problem in problems:
        print(f"FAIL {problem}")
    print("sandbox check passed" if passed else "sandbox check failed")
    return 0 if passed else 1


def _run(args: argparse.Namespace) -> int:
    from onboard.model_client import client_for
    from onboard.run import run_task
    from onboard.sandbox import docker_sandbox, require_check
    from onboard.task import resolve_task

    config = load_config(args.config).with_overrides(model=args.model, effort=args.effort)
    sandbox = docker_sandbox(config)
    require_check(config.sandbox.digest)
    result = run_task(resolve_task(args.task), config, client_for(config), sandbox)
    print(f"{result.run_dir}: {result.outcome.status}. {result.outcome.reason}")
    return 0 if result.outcome.status == "passed" else 1


def _eval(args: argparse.Namespace) -> int:
    from onboard.evaluate import evaluate, safe_hidden_checks, write_results
    from onboard.model_client import client_for
    from onboard.sandbox import docker_sandbox, require_check

    tasks = sorted((ROOT / "tasks").glob("R*.yaml"))
    if not args.runs and not tasks:
        print(
            "no frozen tasks in tasks/R*.yaml; choose and freeze R1-R3 first (spec 17.1)",
            file=sys.stderr,
        )
        return 2
    config = load_config(args.config).with_overrides(model=args.model, effort=args.effort)
    sandbox = docker_sandbox(config)
    require_check(config.sandbox.digest)
    if args.runs:
        results = [safe_hidden_checks(Path(run), sandbox) for run in args.runs]
        path = write_results(results, ["Hidden checks on existing runs; no new runs."])
    else:
        client_for(config)  # fail before any run if the provider's key is missing
        path = evaluate(tasks, config, lambda: client_for(config), sandbox)
    print(f"wrote {path}")
    return 0


def _rerun(args: argparse.Namespace) -> int:
    from onboard.manifest import read_manifest
    from onboard.rerun import rerun
    from onboard.sandbox import require_check

    require_check(read_manifest(Path(args.directory))["sandbox"]["digest"])
    steps = rerun(Path(args.directory))
    for step in steps:
        print(f"{'pass' if step.ok else 'FAIL'}  {step.name}: {step.detail}")
    return 0 if all(step.ok for step in steps) else 1


def _replay(args: argparse.Namespace) -> int:
    from onboard.manifest import read_manifest
    from onboard.replay import replay
    from onboard.sandbox import docker_sandbox, require_check

    config = load_config(args.config)
    sandbox = docker_sandbox(config)
    require_check(config.sandbox.digest)
    original = read_manifest(Path(args.run_dir))
    result = replay(Path(args.run_dir), config, sandbox)
    same = result.outcome.status == original["status"]
    print(
        json.dumps(
            {
                "replay_dir": str(result.run_dir),
                "original_status": original["status"],
                "replay_status": result.outcome.status,
                "same_status": same,
            },
            indent=2,
        )
    )
    return 0 if same else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="onboard", description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="download and freeze a deposit")
    fetch.add_argument("study_id")
    fetch.set_defaults(handler=_fetch)

    check = commands.add_parser("check-sandbox", help="verify the image and run the probe")
    check.add_argument("--build", action="store_true", help="rebuild and record the image ID")
    check.set_defaults(handler=_check_sandbox)

    run = commands.add_parser("run", help="one agent run")
    run.add_argument("task", type=Path)
    run.add_argument("--model")
    run.add_argument("--effort")
    run.set_defaults(handler=_run)

    evaluation = commands.add_parser("eval", help="runs on R1-R3 plus hidden checks")
    evaluation.add_argument("--model")
    evaluation.add_argument("--effort")
    evaluation.add_argument("--runs", nargs="+", help="only run hidden checks on these runs")
    evaluation.set_defaults(handler=_eval)

    rerun = commands.add_parser("rerun", help="model-free re-run and comparison")
    rerun.add_argument("directory")
    rerun.set_defaults(handler=_rerun)

    replay = commands.add_parser("replay", help="re-drive a run from its log, no API calls")
    replay.add_argument("run_dir")
    replay.set_defaults(handler=_replay)

    args = parser.parse_args(argv)
    code: int = args.handler(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
