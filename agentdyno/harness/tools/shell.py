"""Run a shell command in a scoped working directory with a timeout."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


def run_shell(command: str, cwd: str, timeout_s: float = 30.0) -> ShellResult:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return ShellResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired as e:
        return ShellResult(
            stdout=e.stdout or "",
            stderr=(e.stderr or "") + "\n[agentdyno] command timed out",
            exit_code=-1,
            timed_out=True,
        )
