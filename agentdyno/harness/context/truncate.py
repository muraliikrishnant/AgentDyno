"""Simple context truncation: keep the system message and the most recent
N messages, dropping the middle when the window is under pressure."""
from __future__ import annotations


def truncate_messages(messages: list[dict], max_messages: int = 20) -> list[dict]:
    if len(messages) <= max_messages:
        return messages
    system = [m for m in messages if m["role"] == "system"][:1]
    rest = [m for m in messages if m["role"] != "system"]
    keep = rest[-(max_messages - len(system)):]
    return system + keep
