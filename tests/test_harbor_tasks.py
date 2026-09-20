from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = REPO_ROOT / "experiments" / "tasks"


def test_all_toy_tasks_have_complete_harbor_packages() -> None:
    task_dirs = sorted(
        path
        for path in TASKS_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("task") and (path / "broken.py").exists()
    )

    assert len(task_dirs) == 5
    names: set[str] = set()
    for task_dir in task_dirs:
        manifest = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        task = manifest["task"]
        assert manifest["schema_version"] == "1.4"
        assert task["name"].startswith("agentdyno/")
        assert task["name"] not in names
        names.add(task["name"])
        assert manifest["environment"]["docker_image"] == "python:3.12-slim"
        assert manifest["environment"]["workdir"] == "/app"
        assert "network_mode" not in manifest["environment"]

        assert (task_dir / "instruction.md").read_text(encoding="utf-8").strip() == (
            task_dir / "instruction.txt"
        ).read_text(encoding="utf-8").strip()
        assert (task_dir / "environment" / "broken.py").read_bytes() == (
            task_dir / "broken.py"
        ).read_bytes()
        assert (task_dir / "solution" / "solution.py").read_bytes() == (
            task_dir / "solution.py"
        ).read_bytes()
        assert (task_dir / "solution" / "solve.sh").is_file()
        assert (task_dir / "tests" / "test.sh").is_file()


def test_each_harbor_task_verifies_its_solution() -> None:
    task_dirs = sorted(
        path
        for path in TASKS_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("task") and (path / "broken.py").exists()
    )

    for task_dir in task_dirs:
        with tempfile.TemporaryDirectory() as temporary_dir:
            fixture = Path(temporary_dir)
            shutil.copy2(task_dir / "solution.py", fixture / "broken.py")
            shutil.copy2(task_dir / "test_broken.py", fixture / "test_broken.py")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "test_broken.py"],
                cwd=fixture,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, (
                f"{task_dir.name} solution did not satisfy its tests:\n"
                f"{result.stdout}\n{result.stderr}"
            )
