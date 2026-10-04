"""Fakes for harness tests: scripted model responses and a sandbox that runs only trusted code.

FakeSandbox never executes the submitted version. It runs the reference converter
(or a broken variant) in-process on the host, which is allowed because that code is
written for this repository, and returns a canned result for the version's tests.
"""

from __future__ import annotations

import io
import itertools
from collections.abc import Callable
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

from onboard.model_client import ModelResponse, Usage
from onboard.sandbox import Execution
from reference import workbench_rest
from reference.broken import build_variant

_ids = itertools.count(1)


def tool_use(name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": arguments}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def response(stop_reason: str, *blocks: dict[str, Any], tokens: int = 100) -> ModelResponse:
    return ModelResponse(
        id=f"msg_{next(_ids)}",
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=list(blocks),
        usage=Usage(input_tokens=tokens, output_tokens=tokens),
        seconds=0.01,
    )


def submit(prepare_code: str = "def prepare(a, b, c, d):\n    pass\n") -> dict[str, Any]:
    return tool_use(
        "submit_converter",
        prepare_code=prepare_code,
        test_code="from prepare import prepare\n\ndef test_x():\n    pass\n",
        notes="first try",
    )


def load_variant(variant: str) -> Any:
    """A broken variant as an importable module (dataclasses need it in sys.modules)."""
    import importlib.util
    import sys
    import tempfile

    path = Path(tempfile.mkdtemp()) / f"fake_{variant}.py"
    path.write_text(build_variant(variant))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


class FakeSandbox:
    image = "sha256:fake"

    def __init__(
        self,
        variant: str | None = None,
        tests_pass: bool | Callable[[Path], bool] = True,
        timeout: bool = False,
    ):
        self.module = workbench_rest if variant is None else load_variant(variant)
        self.tests_pass = tests_pass
        self.timeout = timeout
        self.converter_runs: list[tuple[Path, Path, Path]] = []

    def run_converter(self, code_dir: Path, input_dir: Path, output_dir: Path) -> Execution:
        self.converter_runs.append((code_dir, input_dir, output_dir))
        if self.timeout:
            return Execution(None, "", "stopped after 120 seconds", 120.0, True)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = self.module.main(
                [
                    "--factors",
                    str(input_dir / "factors.json"),
                    "--data",
                    str(input_dir / "data.json"),
                    "--task",
                    str(input_dir / "task.yaml"),
                    "--output",
                    str(output_dir),
                ]
            )
        return Execution(code, "", stderr.getvalue(), 0.1, False)

    def run_tests(self, code_dir: Path) -> Execution:
        passes = self.tests_pass(code_dir) if callable(self.tests_pass) else self.tests_pass
        if passes:
            return Execution(0, "3 passed in 0.1s\n", "", 0.2, False)
        out = "___ test_ids ___\nassert '1' == '01'\n1 failed, 2 passed in 0.1s\n"
        return Execution(1, out, "", 0.2, False)
