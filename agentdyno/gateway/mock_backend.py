"""Local mock model backend simulating streaming TTFT/ITL so the gateway and
profiler have real (synthetic) telemetry to work with when no Nebius/Nemotron
credentials are configured.

# TODO(nebius): replace with real Nebius Token Factory OpenAI-compatible
# endpoint calls once credentials are available (see agentdyno/gateway/proxy.py).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

TIER_LATENCY_PROFILES = {
    "nano": {"ttft_ms": (60, 150), "itl_ms": (8, 20)},
    "super": {"ttft_ms": (150, 400), "itl_ms": (15, 35)},
    "ultra": {"ttft_ms": (400, 900), "itl_ms": (25, 55)},
}

_FIXED_RESPONSES = [
    "I'll look at the failing test to understand what's expected.",
    "The function has an off-by-one error; let me fix it.",
    "Running the test suite to confirm the fix works.",
    "All tests pass now. The task is complete.",
    "Let me inspect the file contents before editing.",
]


@dataclass
class MockChunk:
    delta_text: str
    is_final: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class MockModelBackend:
    """Simulates a streaming chat-completions call with plausible TTFT/ITL.

    Not a real model: deterministic-ish content, randomized-but-plausible
    latencies keyed off a `tier` string (nano/super/ultra) so different
    experiment conditions produce visibly different telemetry.
    """

    seed: int | None = None
    _rng: random.Random = field(default_factory=random.Random, init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def stream(self, messages: list[dict], tier: str = "super"):
        """Yields (chunk_text, timestamp) tuples, blocking realistically."""
        profile = TIER_LATENCY_PROFILES.get(tier, TIER_LATENCY_PROFILES["super"])
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages) + 8

        text = self._rng.choice(_FIXED_RESPONSES)
        tokens = text.split()

        ttft_s = self._rng.uniform(*profile["ttft_ms"]) / 1000.0
        time.sleep(ttft_s)
        t_first = time.monotonic()
        yield tokens[0] + " ", t_first

        for tok in tokens[1:]:
            itl_s = self._rng.uniform(*profile["itl_ms"]) / 1000.0
            time.sleep(itl_s)
            yield tok + " ", time.monotonic()

        # `return` (not shared instance state) so usage travels back to the
        # caller via StopIteration.value - safe under concurrent callers
        # (e.g. the subagents architecture's real concurrent threads), unlike
        # a self._last_usage attribute on this shared MockModelBackend instance.
        return {"prompt_tokens": prompt_tokens, "completion_tokens": len(tokens)}
