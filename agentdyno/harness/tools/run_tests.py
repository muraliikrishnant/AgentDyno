"""Run pytest (or a given test command) in the task directory and capture pass/fail."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from agentdyno.harness.tools.shell import run_shell


@dataclass
class TestResult:
    passed: bool
    stdout: str
    stderr: str
    exit_code: int


def run_tests(cwd: str, command: str | None = None, timeout_s: float = 30.0) -> TestResult:
    command = command or f"{sys.executable} -m pytest -q"
    result = run_shell(command, cwd=cwd, timeout_s=timeout_s)
    return TestResult(
        passed=(result.exit_code == 0 and not result.timed_out),
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
    )
