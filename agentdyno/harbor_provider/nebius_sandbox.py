"""Harbor sandbox environment providers.

`NebiusSandboxEnvironment` is the upstream-able Harbor `BaseEnvironment`
implementation backed by Nebius Token Factory Sandboxes (the "ConTree"
platform, pip package `contree-sdk`; microVM isolation, checkpoint/branch).
It now really subclasses `harbor.environments.base.BaseEnvironment` and
implements every abstract method against the `contree-sdk` client surface
documented at docs.tokenfactory.nebius.com/sandboxes/. Several exact details
(the Sandboxes API `base_url`, and a couple of method names for file
transfer) could not be confirmed from the docs pages reachable during this
session, and are marked `# TODO(nebius):` below with precise instructions
for resolving them. Everything else - client construction, image use,
command exec, lifecycle, error handling - is implemented for real, modeled
directly on Harbor's own `E2BEnvironment` (harbor/environments/e2b.py), the
simplest existing cloud-sandbox provider in the installed `harbor` package.

`LocalSubprocessEnvironment` (bottom of this file) is unchanged: the working
local fallback used by `agentdyno.cli` today, no Docker/Nebius required.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.definition import effective_exec_cwd

# contree-sdk (Nebius Sandboxes / "ConTree") is an optional dependency -
# install with `pip install agentdyno[nebius-sandbox]`. Import lazily so the
# rest of AgentDyno (mock/local runs, single/subagents orchestration, the
# gateway) never requires it.
try:
    from contree_client.httpx import ContreeAsyncClient
    from contree_sdk import Contree

    _HAS_CONTREE = True
except ImportError:
    _HAS_CONTREE = False
    ContreeAsyncClient = None  # type: ignore[assignment,misc]
    Contree = None  # type: ignore[assignment,misc]


class NebiusSandboxMissingDependencyError(RuntimeError):
    """Raised when NebiusSandboxEnvironment is used without contree-sdk installed."""

    def __init__(self) -> None:
        super().__init__(
            "NebiusSandboxEnvironment requires the `contree-sdk` package "
            "(Nebius Sandboxes / \"ConTree\"). Install it with: "
            "`pip install agentdyno[nebius-sandbox]` (or `pip install "
            "contree-sdk` directly), then retry."
        )


class NebiusSandboxConfigError(RuntimeError):
    """Raised when required Nebius Sandboxes configuration is missing."""


class NebiusSandboxEnvironment(BaseEnvironment):
    """Harbor `BaseEnvironment` backed by Nebius Token Factory Sandboxes.

    Construction mirrors `E2BEnvironment.__init__`: it accepts all of
    BaseEnvironment's standard kwargs plus two Nebius-specific ones,
    `base_image` (the sandbox image to `sdk.images.use(...)`, falling back to
    `task_env_config.docker_image`) and `api_key`/`base_url` overrides.
    """

    def __init__(
        self,
        environment_dir: Path,
        environment_name: str,
        session_id: str,
        trial_paths: Any,
        task_env_config: Any,
        *args,
        base_image: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ):
        if not _HAS_CONTREE:
            raise NebiusSandboxMissingDependencyError()

        super().__init__(
            environment_dir=environment_dir,
            environment_name=environment_name,
            session_id=session_id,
            trial_paths=trial_paths,
            task_env_config=task_env_config,
            **kwargs,
        )

        self._api_key = api_key or os.environ.get("NEBIUS_API_KEY")
        if not self._api_key:
            raise NebiusSandboxConfigError(
                "NebiusSandboxEnvironment requires NEBIUS_API_KEY (env var or "
                "api_key=...)."
            )

        # TODO(nebius): confirm the real Sandboxes API base_url. The Token
        # Factory *inference* base_url (NEBIUS_BASE_URL, used by
        # agentdyno/gateway/proxy.py) is confirmed working, but the docs
        # pages reachable during this session did not publish a distinct
        # Sandboxes endpoint. Try, in order: (1) a dedicated
        # NEBIUS_SANDBOXES_BASE_URL env var if the user's Sandboxes console
        # documents one, (2) the Sandboxes console's "API" tab for a
        # project-specific base_url, (3) contree_client's own default (some
        # SDKs ship a working default and only need the api_key). Until
        # confirmed, this falls back to the inference base_url's host with
        # a guessed `/sandboxes` path, which is very likely wrong - it exists
        # only so `start()` fails with a clear connection/auth error instead
        # of a confusing AttributeError.
        self._base_url = (
            base_url
            or os.environ.get("NEBIUS_SANDBOXES_BASE_URL")
            or (os.environ.get("NEBIUS_BASE_URL", "").rstrip("/") + "/sandboxes")
        )

        self._base_image = base_image or task_env_config.docker_image or "python:3.12-slim"

        self._api_client: Any = None
        self._sdk: Any = None
        self._image: Any = None
        self._sandbox: Any = None  # result of image.run(...) session, if the
        # SDK models a persistent handle separately from per-command results;
        # see start()/exec() for how this is used.

    # -- BaseEnvironment required overrides ---------------------------------

    @staticmethod
    def type() -> str:
        # Returned as a plain str (not an EnvironmentType enum member) per
        # BaseEnvironment.type()'s own docstring: third-party environments
        # outside the harbor repo don't need to modify harbor's enum.
        # TODO(harbor): once upstreamed, add EnvironmentType.NEBIUS to
        # harbor/models/environment_type.py and register this class in
        # harbor/environments/factory.py's _ENVIRONMENT_REGISTRY, matching
        # every other built-in provider (see factory.py in the installed
        # harbor package for the pattern - it's a simple dict entry).
        return "nebius"

    def _validate_definition(self):
        # Nebius Sandboxes run from a named image (`sdk.images.use(...)`),
        # not a Dockerfile build like Docker/Podman/E2B's dockerfile path.
        # Nothing to validate on disk beyond task_env_config carrying either
        # a docker_image or having accepted this class's base_image default.
        if not (self._base_image if hasattr(self, "_base_image") else True):
            raise ValueError("NebiusSandboxEnvironment requires a base image.")

    async def start(self, force_build: bool) -> None:
        try:
            self._api_client = ContreeAsyncClient(self._api_key, base_url=self._base_url)
            self._sdk = Contree(self._api_client)
            self._image = await self._sdk.images.use(self._base_image)
        except Exception as e:  # noqa: BLE001 - surface a clear, actionable error
            raise RuntimeError(
                f"NebiusSandboxEnvironment.start failed to initialize a "
                f"Nebius Sandbox against base_url={self._base_url!r} with "
                f"image={self._base_image!r}: {e}. If this is a connection "
                f"or 404/auth error, the base_url TODO in __init__ is almost "
                f"certainly the cause - confirm the real Sandboxes API "
                f"base_url in the Nebius console and pass it as "
                f"base_url=... or NEBIUS_SANDBOXES_BASE_URL."
            ) from e

        await self._upload_environment_dir_after_start()

    async def stop(self, delete: bool) -> None:
        # TODO(nebius): the docs pages fetched during this session did not
        # surface an explicit sandbox stop/delete/teardown method distinct
        # from image/run session objects going out of scope. If contree-sdk
        # exposes one (check `python -c "import contree_sdk;
        # help(contree_sdk.Contree)"` after installing the extra), call it
        # here, e.g. `await self._sandbox.stop()` /
        # `await self._sdk.sandboxes.delete(...)`. Until confirmed, this
        # just drops references so the client/session are garbage collected
        # rather than raising, so trial teardown never hard-fails on this
        # unresolved detail.
        self._sandbox = None
        self._image = None
        self._sdk = None
        self._api_client = None

    async def upload_file(self, source_path: Path | str, target_path: str):
        # TODO(nebius): confirm exact method name/signature for single-file
        # upload on contree-sdk's `image`/sandbox object (the docs pages
        # fetched described `image.run(shell=...)` for command execution but
        # not a dedicated file-write API). Modeled here on the pattern every
        # other Harbor provider uses (e2b: `sandbox.files.write(path, bytes)`,
        # daytona: similar) as the most likely real shape.
        data = Path(source_path).read_bytes()
        if hasattr(self._image, "files") and hasattr(self._image.files, "write"):
            await self._image.files.write(target_path, data)
            return
        raise NotImplementedError(
            "NebiusSandboxEnvironment.upload_file: contree-sdk's file-write "
            "API was not confirmed from available docs. Inspect "
            "`help(contree_sdk.Contree)` / `help(<image object>)` after "
            "`pip install contree-sdk` to find the real method and wire it "
            "in here (see TODO(nebius) comment above)."
        )

    async def upload_dir(self, source_dir: Path | str, target_dir: str):
        source_dir = Path(source_dir)
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(source_dir).as_posix()
                await self.upload_file(file_path, f"{target_dir.rstrip('/')}/{rel}")

    async def download_file(self, source_path: str, target_path: Path | str):
        # TODO(nebius): same as upload_file - exact read/download method name
        # unconfirmed. Modeled on e2b's `sandbox.files.read(path,
        # format="bytes")`.
        if hasattr(self._image, "files") and hasattr(self._image.files, "read"):
            data = await self._image.files.read(source_path)
            Path(target_path).write_bytes(data)
            return
        raise NotImplementedError(
            "NebiusSandboxEnvironment.download_file: contree-sdk's file-read "
            "API was not confirmed from available docs. See TODO(nebius) "
            "comment above upload_file for how to resolve this."
        )

    async def download_dir(self, source_dir: str, target_dir: Path | str):
        # TODO(nebius): requires a directory-listing API on contree-sdk to
        # walk source_dir remotely (see e2b's `sandbox.files.list(...)` for
        # the pattern this should follow once confirmed). Unconfirmed from
        # available docs, so this raises rather than silently downloading
        # nothing.
        raise NotImplementedError(
            "NebiusSandboxEnvironment.download_dir: contree-sdk's directory-"
            "listing API was not confirmed from available docs. See "
            "TODO(nebius) comments above for how to resolve this once the "
            "SDK is installed and introspected."
        )

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        if self._image is None:
            raise RuntimeError(
                "NebiusSandboxEnvironment.exec called before start() "
                "succeeded."
            )

        shell_cmd = command
        resolved_cwd = effective_exec_cwd(cwd, self.task_env_config.workdir, None)
        if resolved_cwd:
            shell_cmd = f"cd {resolved_cwd!r} && {shell_cmd}"
        if env:
            export_prefix = " && ".join(f"export {k}={v!r}" for k, v in env.items())
            shell_cmd = f"{export_prefix} && {shell_cmd}"

        try:
            result = await self._image.run(shell=shell_cmd)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"NebiusSandboxEnvironment.exec failed running {command!r}: "
                f"{e}"
            ) from e

        return ExecResult(
            stdout=getattr(result, "stdout", None),
            stderr=getattr(result, "stderr", None),
            return_code=getattr(result, "exit_code", 1),
        )

    # -- Checkpoint/branch (Nebius-specific, not part of BaseEnvironment) ---
    # The plan doc (section 4/10) wants checkpoint/branch semantics for
    # profiling backtracking architectures. contree-sdk's docs describe
    # "fork execution state at any checkpoint" / "return to any previous
    # state" at a conceptual level; the exact method names were not
    # confirmed from the docs pages reached during this session.

    async def checkpoint(self, name: str) -> str:
        # TODO(nebius): confirm the real checkpoint API, e.g.
        # `await self._image.checkpoint(name=name)` or
        # `await self._sdk.checkpoints.create(...)`. Likely candidates based
        # on the "fork execution state" / "return to any previous state"
        # language in the docs summary, but unconfirmed.
        raise NotImplementedError(
            "NebiusSandboxEnvironment.checkpoint: contree-sdk's checkpoint "
            "API was not confirmed from available docs. See module "
            "docstring for what to check once contree-sdk is installed."
        )

    async def branch(self, checkpoint_name: str) -> "NebiusSandboxEnvironment":
        # TODO(nebius): see checkpoint() above.
        raise NotImplementedError(
            "NebiusSandboxEnvironment.branch: contree-sdk's branch/fork API "
            "was not confirmed from available docs. See module docstring."
        )


class LocalSubprocessEnvironment:
    """Working local fallback: runs commands in a temp directory copied from
    a task source directory. No Docker, no Nebius - available today, still
    used by agentdyno.cli's `run` command."""

    def __init__(self, task_dir: str):
        self.task_dir = task_dir
        self.workdir: str = ""
        self._tmp: str = ""

    def start(self) -> str:
        import shutil
        import tempfile

        self._tmp = tempfile.mkdtemp(prefix="agentdyno_")
        dest = Path(self._tmp) / "task"
        shutil.copytree(self.task_dir, dest)
        self.workdir = str(dest)
        return self.workdir

    def exec(self, command: str, timeout_s: float = 30.0):
        from agentdyno.harness.tools.shell import run_shell

        if not self.workdir:
            raise RuntimeError("call start() first")
        return run_shell(command, cwd=self.workdir, timeout_s=timeout_s)

    def checkpoint(self, name: str) -> str:
        import shutil

        snap_dir = Path(self._tmp) / f"checkpoint_{name}"
        shutil.copytree(self.workdir, snap_dir, dirs_exist_ok=True)
        return str(snap_dir)

    def branch(self, checkpoint_path: str) -> str:
        import shutil

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
        import shutil

        if delete and self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
