"""Tracks cumulative estimated USD spend against real Nebius Token Factory
calls and refuses new calls once a configurable ceiling is crossed.

This is a safety net on top of (not a replacement for) a spend limit set in
the Nebius console itself - it estimates cost from token counts and the
placeholder pricing in agentdyno.profiler.derive.PRICE_PER_1K_TOKENS, which
is not yet confirmed against live pricing, so it should not be trusted as
exact. Keep the ceiling comfortably under your real budget.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from agentdyno.profiler.derive import PRICE_PER_1K_TOKENS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEDGER_PATH = DATA_DIR / "spend_ledger.json"

SPEND_CEILING_USD = float(os.environ.get("AGENTDYNO_SPEND_CEILING_USD", "40.0"))

_lock = threading.Lock()


class SpendCeilingExceeded(RuntimeError):
    pass


def _read_ledger() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return {"total_usd": 0.0}


def _write_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))


def current_spend_usd() -> float:
    with _lock:
        return _read_ledger()["total_usd"]


def estimate_cost(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICE_PER_1K_TOKENS.get(tier, PRICE_PER_1K_TOKENS["super"])
    return (prompt_tokens / 1000) * price["prompt"] + (completion_tokens / 1000) * price["completion"]


def check_before_call(tier: str, estimated_prompt_tokens: int = 0) -> None:
    """Raise SpendCeilingExceeded if even a small worst-case call would push
    total spend past the ceiling. Called before every real Nebius request."""
    with _lock:
        ledger = _read_ledger()
        if ledger["total_usd"] >= SPEND_CEILING_USD:
            raise SpendCeilingExceeded(
                f"AgentDyno spend ceiling reached: ${ledger['total_usd']:.4f} "
                f">= ${SPEND_CEILING_USD:.2f}. Refusing further Nebius calls. "
                f"Raise AGENTDYNO_SPEND_CEILING_USD to override."
            )


def record_spend(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Add a real call's estimated cost to the ledger, return new total."""
    cost = estimate_cost(tier, prompt_tokens, completion_tokens)
    with _lock:
        ledger = _read_ledger()
        ledger["total_usd"] = ledger["total_usd"] + cost
        _write_ledger(ledger)
        return ledger["total_usd"]
