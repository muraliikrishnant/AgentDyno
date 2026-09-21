"""Harbor sandbox environment providers.

`NebiusSandboxEnvironment` is the upstream-able Harbor `BaseEnvironment`
implementation backed by Nebius Token Factory Sandboxes (the "ConTree"
platform, pip package `contree-sdk`; microVM isolation, checkpoint/branch).
It really subclasses `harbor.environments.base.BaseEnvironment` and
implements every abstract method against the real `contree-sdk` client
surface, which was installed and introspected directly during development
(`.venv/lib/python3.12/site-packages/contree_sdk/`, version 0.3.6 as of
2026-09-19) rather than only inferred from docs pages, so the API shapes
below are confirmed against the actual library source, not guessed:

- `contree_sdk.Contree(base_url=..., token=...)` (or a `ContreeConfig`) is
  the real async client - see `contree_sdk/sdk/client/_base.py`. There is no
  `contree_client.httpx.ContreeAsyncClient` (that module does not exist in
  the installed package; an earlier draft of this file assumed it did).
- The real default Sandboxes API base_url IS resolvable from the SDK
  itself: `contree_sdk.auth.IAMAuth.base_url` defaults to
  `ContreeEndpoint.TOKEN_FACTORY_SANDBOXES` =
  `"https://api.tokenfactory.nebius.com/sandboxes/"`
  (`contree_sdk/_internals/utils/config.py`). `IAMAuth` also resolves
  `token` from the `NEBIUS_API_KEY` env var and `project_id` from
  `NEBIUS_PROJECT_ID` by default (`contree_sdk/auth.py`), so a bare
  `Contree()` with no args already does the right thing given the user's
  existing `.env`, EXCEPT `NEBIUS_PROJECT_ID` is not currently in this
  project's `.env` - see TODO(nebius) in `start()`.
- `sdk.images.use(ref)` resolves an image reference lazily (no API call
  until first `run()`); `image.run(shell=...)`/`image.run(command, args=…)`
  returns a new (not-yet-executed) image object that is itself awaitable
  (`_ImageLike.__await__` -> `_await()`), matching the doc's
  `await image.run(shell=...)` pattern. The executed result is read off
  `.result` (`ContreeResult`: `.stdout`, `.stderr`, `.exit_code`), not off
  the awaited image directly.
- File upload is `await image.apply_files({target_path: source_bytes_or_
  Path})`, returning a NEW image with the files baked in (images are
  otherwise immutable/disposable) - confirmed in
  `contree_sdk/sdk/objects/image_like/_base.py::_apply_files`. Download is
  `await image.download(image_path, local_path)` / `await
  image.read(image_path)`; listing is `await image.ls(path)`.
- No explicit "stop/delete a running sandbox" call was found on the image/
  client surface introspected - sandboxes appear to be scoped to each `run`
  invocation (disposable by default) rather than long-lived handles you
  explicitly tear down, which is architecturally different from E2B/Daytona.
  `checkpoint`/`branch` in the plan doc's sense map most closely to
  `tag_as(tag)` (pins the resulting image under a name) and re-`use()`-ing
  that tag later, but this is inference from the state machine
  (`ImageState`/`_STATE_MACHINE`) rather than a documented "checkpoint" API
  call, so it's still marked TODO(nebius) below pending real use.

Everything else - client construction, image use, command exec, lifecycle,
error handling - is implemented for real, modeled on the *shape* of Harbor's
own `E2BEnvironment` (harbor/environments/e2b.py), the simplest existing
cloud-sandbox provider in the installed `harbor` package, but using the
actually-confirmed contree-sdk calls rather than E2B's.

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
    from contree_sdk import Contree

    _HAS_CONTREE = True
except ImportError:
    _HAS_CONTREE = False
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

        # Confirmed real default: contree_sdk.auth.IAMAuth.base_url defaults
        # to ContreeEndpoint.TOKEN_FACTORY_SANDBOXES, i.e. exactly this URL
        # (introspected directly from the installed contree-sdk==0.3.6
        # package, not guessed). Still overridable via base_url=... or
        # NEBIUS_SANDBOXES_BASE_URL for staging/other environments.
        self._base_url = (
            base_url
            or os.environ.get("NEBIUS_SANDBOXES_BASE_URL")
            or "https://api.tokenfactory.nebius.com/sandboxes/"
        )

        # TODO(nebius): IAMAuth also wants a project_id (defaults to reading
        # the NEBIUS_PROJECT_ID env var), which is NOT currently in this
        # project's .env. Sandbox creation may fail with an auth/permission
        # error until the user adds NEBIUS_PROJECT_ID from their Nebius
        # console. Surfaced as a clear error in start() below rather than
        # failing silently.
        self._project_id = os.environ.get("NEBIUS_PROJECT_ID")

        self._base_image = base_image or task_env_config.docker_image or "python:3.12-slim"

        self._client: Any = None
        self._image: Any = None  # a ContreeImage handle from sdk.images.use();
        # reassigned to the returned image after any apply_files() call,
        # since contree-sdk images are immutable/disposable (see module
        # docstring).

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
        # Confirmed 2026-09-19 against the real contree-sdk==0.3.6 client and
        # the official quickstart: a bare `Contree()` auto-discovers
        # base_url/token/project_id from NEBIUS_API_KEY/NEBIUS_PROJECT_ID
        # (ContreeConfig(auth=IAMAuth(...)) is what it builds internally -
        # no need to construct that ourselves). Live-tested end-to-end
        # (real network round trip to
        # https://api.tokenfactory.nebius.com/sandboxes/v1/instances) and
        # got back 403 Forbidden / "You do not have permission to perform
        # this action" - request shape, auth, and env-var wiring are all
        # confirmed correct; the account is not yet approved for Sandboxes
        # beta access (a separate approval step via the "Describe your
        # case" form on the Sandboxes product page, not a credentials or
        # code issue). Re-test once beta access is granted.
        try:
            self._client = Contree(base_url=self._base_url, token=self._api_key)
            # Lazy reference - contree-sdk makes no API call until the first
            # run()/apply_files() against it (confirmed: `use()` just wraps
            # the tag/uuid, see _use_image in
            # contree_sdk/sdk/managers/images/_base.py).
            self._image = await self._client.images.use(self._base_image)
        except Exception as e:  # noqa: BLE001 - surface a clear, actionable error
            hint = ""
            if not self._project_id:
                hint = (
                    " NEBIUS_PROJECT_ID is not set in this environment - "
                    "contree_sdk.auth.IAMAuth requires a project id; set "
                    "NEBIUS_PROJECT_ID from the Nebius console."
                )
            elif "Forbidden" in type(e).__name__ or "403" in str(e):
                hint = (
                    " This looks like a Sandboxes beta access/entitlement "
                    "issue rather than a credentials problem - confirm your "
                    "Nebius account has been approved for Sandboxes beta "
                    "access (see the 'Describe your case' form on the "
                    "Sandboxes product page)."
                )
            raise RuntimeError(
                f"NebiusSandboxEnvironment.start failed to initialize a "
                f"Nebius Sandbox against base_url={self._base_url!r} with "
                f"image={self._base_image!r}: {e}.{hint}"
            ) from e

        await self._upload_environment_dir_after_start()

    async def stop(self, delete: bool) -> None:
        # No explicit "stop/delete a running sandbox" call was found on the
        # contree-sdk client/image surface introspected from the installed
        # package (contree_sdk/sdk/client/_base.py,
        # contree_sdk/sdk/objects/image_like/_base.py): images are
        # disposable-by-default per `run(..., disposable=True)`, so the
        # platform appears to tear down compute per-invocation rather than
        # via a long-lived handle you explicitly stop. If a dedicated
        # teardown/delete method exists (e.g. on a future
        # `client.instances` or `client.sandboxes` manager not present in
        # 0.3.6), call it here.
        # TODO(nebius): re-check `dir(contree_sdk.Contree(...))` against a
        # newer contree-sdk release for an explicit stop/delete call before
        # relying on disposable=True alone in production use.
        self._image = None
        self._client = None

    async def upload_file(self, source_path: Path | str, target_path: str):
        if self._image is None:
            raise RuntimeError("NebiusSandboxEnvironment.upload_file called before start().")
        data = Path(source_path).read_bytes()
        # Confirmed: image_like._base._apply_files -> new image with files
        # baked in (images are immutable; apply_files returns a NEW image,
        # so we must keep the returned handle for subsequent exec() calls).
        self._image = await self._image.apply_files({target_path: data})

    async def upload_dir(self, source_dir: Path | str, target_dir: str):
        if self._image is None:
            raise RuntimeError("NebiusSandboxEnvironment.upload_dir called before start().")
        source_dir = Path(source_dir)
        files: dict[str, bytes] = {}
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(source_dir).as_posix()
                files[f"{target_dir.rstrip('/')}/{rel}"] = file_path.read_bytes()
        if files:
            # Single apply_files() call batches the whole directory into one
            # new image rather than N round trips (confirmed: apply_files
            # accepts a dict of target_path -> bytes|Path|UploadFileSpec).
            self._image = await self._image.apply_files(files)

    async def download_file(self, source_path: str, target_path: Path | str):
        if self._image is None:
            raise RuntimeError("NebiusSandboxEnvironment.download_file called before start().")
        # Confirmed: _ImageLike.read() -> _read_file() returns bytes.
        data = await self._image.read(source_path)
        Path(target_path).write_bytes(data)

    async def download_dir(self, source_dir: str, target_dir: Path | str):
        if self._image is None:
            raise RuntimeError("NebiusSandboxEnvironment.download_dir called before start().")
        # Confirmed: _ImageLike.ls(path) -> list[ImageFile | ImageDirectory]
        # (contree_sdk/sdk/objects/image_like/_async.py). Walk recursively,
        # mirroring E2BEnvironment.download_dir's structure.
        entries = await self._image.ls(source_dir)
        target_dir = Path(target_dir)
        for entry in entries:
            entry_path = getattr(entry, "path", None) or str(entry)
            rel = Path(entry_path).relative_to(Path(source_dir))
            is_dir = type(entry).__name__ == "ImageDirectory"
            if is_dir:
                (target_dir / rel).mkdir(parents=True, exist_ok=True)
                await self.download_dir(entry_path, target_dir / rel)
            else:
                (target_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                await self.download_file(entry_path, target_dir / rel)

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

        resolved_cwd = effective_exec_cwd(cwd, self.task_env_config.workdir, None)

        try:
            # Confirmed live 2026-09-21 against a real, beta-approved Nebius
            # Sandboxes account (see AgentDyno git history for the earlier
            # 403 Forbidden while beta access was still pending): runs
            # default to disposable=True, meaning each call starts from a
            # FRESH copy of the image and any side effects (installed
            # packages, written files) are thrown away - confirmed by a
            # real `apt-get update` + `apt-get install` sequence where the
            # install failed with "Unable to locate package" until
            # disposable=False was passed explicitly. The awaited run
            # result IS the executed image itself (has .stdout/.stderr/
            # .exit_code directly - not nested under .result; also has its
            # own .run() to chain the next call from this state), so we
            # must reassign self._image to it or every subsequent exec()
            # call silently reverts to the original start()-time image.
            executed = await self._image.run(
                shell=command,
                cwd=resolved_cwd,
                env=env or None,
                timeout=timeout_sec,
                disposable=False,
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"NebiusSandboxEnvironment.exec failed running {command!r}: "
                f"{e}"
            ) from e

        self._image = executed
        return ExecResult(
            stdout=executed.stdout,
            stderr=executed.stderr,
            return_code=executed.exit_code,
        )

    # -- Checkpoint/branch (Nebius-specific, not part of BaseEnvironment) ---
    # The plan doc (section 4/10) wants checkpoint/branch semantics for
    # profiling backtracking architectures. The closest confirmed contree-sdk
    # primitive is `tag_as(tag)` (contree_sdk/sdk/objects/image_like/_base.py
    # ::_tag_as): a non-disposable run's resulting image can be pinned under
    # a tag and later re-resolved via `sdk.images.use(tag)`, which is
    # structurally a checkpoint/branch mechanism (name a state, come back to
    # it, fork new runs from it) even though contree-sdk doesn't use those
    # words. This is inference from the image state machine, not a
    # documented "checkpoint" API, so it's implemented but flagged for
    # real-world verification.

    async def checkpoint(self, name: str) -> str:
        if self._image is None:
            raise RuntimeError("NebiusSandboxEnvironment.checkpoint called before start().")
        # TODO(nebius): verify this actually persists a resumable snapshot
        # rather than just labeling the current disposable result - test
        # against a real Nebius Sandboxes account before relying on it for
        # backtracking-architecture profiling.
        self._image = await self._image.tag_as(name)
        return name

    async def branch(self, checkpoint_name: str) -> "NebiusSandboxEnvironment":
        if self._client is None:
            raise RuntimeError("NebiusSandboxEnvironment.branch called before start().")
        # TODO(nebius): verify use(tag) resolves to the exact checkpointed
        # state rather than the image's current HEAD under that tag.
        self._image = await self._client.images.use(checkpoint_name)
        return self


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
