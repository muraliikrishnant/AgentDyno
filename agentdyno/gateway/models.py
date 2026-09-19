"""Confirmed live Nebius Token Factory model IDs, one per Nemotron tier.

Verified 2026-09-19 against GET /v1/models on api.tokenfactory.nebius.com.
Re-check this if calls start 404ing - the catalog can change.
"""
from __future__ import annotations

TIER_MODEL_IDS = {
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
}


def model_id_for_tier(tier: str) -> str:
    return TIER_MODEL_IDS.get(tier, TIER_MODEL_IDS["super"])
