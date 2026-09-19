"""Harbor sandbox environment providers.

`NebiusSandboxEnvironment` is the planned upstream-able Harbor `Environment`
implementation backed by Nebius Token Factory Sandboxes (microVM isolation,
checkpoint/branch). It is a stub today: the harbor PyPI package's exact
Environment interface and the Token Factory Sandboxes SDK/REST surface need
to be confirmed live before this can be implemented for real (plan doc
section 4/10, Week 2).

`LocalSubprocessEnvironment` is a working fallback used by the CLI today so
the harness has a real environment to execute against without Docker or
Nebius credentials.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agentdyno.harness.tools.shell import ShellResult, run_shell


class NebiusSandboxEnvironment:
    """# TODO(harbor): implement Harbor's Environment protocol
    (start/exec/checkpoint/branch/read_files/stop) against this class once
    the `harbor` PyPI package's Environment ABC is confirmed. Each method
    below documents the intended Nebius Token Factory Sandboxes SDK call.
    """

    def __init__(self, task_repo: str, base_url: str | None = None, api_key: str | None = None):
        self.task_repo = task_repo
        self.base_url = base_url
        self.api_key = api_key

    def start(self):
        # TODO(nebius): POST to Token Factory Sandboxes create-sandbox endpoint
        # (or SDK equivalent, e.g. `nebius.sandboxes.create(image=..., repo=...)`),
        # clone `self.task_repo`, restore the baseline checkpoint.
        raise NotImplementedError("NebiusSandboxEnvironment.start - needs Token Factory Sandboxes SDK/API")

    def exec(self, command: str, timeout_s: float = 30.0):
        # TODO(nebius): call the sandbox's exec endpoint (microVM), stream
        # stdout/stderr, and return exit code - mirrors run_shell's semantics.
        raise NotImplementedError("NebiusSandboxEnvironment.exec - needs Token Factory Sandboxes SDK/API")

    def checkpoint(self, name: str):
        # TODO(nebius): call the Sandboxes checkpoint/snapshot endpoint to
        # capture current filesystem state under `name` for later branch().
        raise NotImplementedError("NebiusSandboxEnvironment.checkpoint - needs Token Factory Sandboxes SDK/API")

    def branch(self, checkpoint_name: str):
        # TODO(nebius): fork a new sandbox instance from a prior checkpoint
        # (git-like branch) to profile backtracking architectures cleanly.
        raise NotImplementedError("NebiusSandboxEnvironment.branch - needs Token Factory Sandboxes SDK/API")

    def read_files(self, paths: list[str]) -> dict[str, str]:
        # TODO(nebius): fetch file contents from the running sandbox via its
        # file-read endpoint/SDK call.
        raise NotImplementedError("NebiusSandboxEnvironment.read_files - needs Token Factory Sandboxes SDK/API")

    def stop(self, delete: bool = True):
        # TODO(nebius): call the Sandboxes stop/delete endpoint to tear down
        # the microVM and release resources.
        raise NotImplementedError("NebiusSandboxEnvironment.stop - needs Token Factory Sandboxes SDK/API")


@dataclass
class LocalSubprocessEnvironment:
    """Working local fallback: runs commands in a temp directory copied from
    a task source directory. No Docker, no Nebius - available today."""

    task_dir: str
    workdir: str = field(default="", init=False)
    _tmp: str = field(default="", init=False)

    def start(self) -> str:
        self._tmp = tempfile.mkdtemp(prefix="agentdyno_")
        dest = Path(self._tmp) / "task"
        shutil.copytree(self.task_dir, dest)
        self.workdir = str(dest)
        return self.workdir

    def exec(self, command: str, timeout_s: float = 30.0) -> ShellResult:
        if not self.workdir:
            raise RuntimeError("call start() first")
        return run_shell(command, cwd=self.workdir, timeout_s=timeout_s)

    def checkpoint(self, name: str) -> str:
        snap_dir = Path(self._tmp) / f"checkpoint_{name}"
        shutil.copytree(self.workdir, snap_dir, dirs_exist_ok=True)
        return str(snap_dir)

    def branch(self, checkpoint_path: str) -> str:
        branch_dir = Path(self._tmp) / f"branch_{Path(checkpoint_path).name}"
        shutil.copytree(checkpoint_path, branch_dir, dirs_exist_ok=True)
        return str(branch_dir)

    def read_files(self, paths: list[str]) -> dict[str, str]:
        out = {}
        for p in paths:
            fp = Path(self.workdir) / p
            out[p] = fp.read_text() if fp.exists() else ""
        return out

    def stop(self, delete: bool = True) -> None:
        if delete and self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
