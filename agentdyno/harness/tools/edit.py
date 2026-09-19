"""Read and write text files within the task working directory."""
from __future__ import annotations

from pathlib import Path


def read_file(path: str) -> str:
    return Path(path).read_text()


def write_file(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
