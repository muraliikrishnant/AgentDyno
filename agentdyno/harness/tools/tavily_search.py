"""Tavily web search tool, profiled as a harness tool round-trip.

# TODO(tavily): call https://api.tavily.com/search with TAVILY_API_KEY when
# set; parse `results` into (title, url, content) tuples. See
# https://docs.tavily.com/documentation/api-reference/endpoint/search.
"""
from __future__ import annotations

import os

import httpx

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")


def tavily_search(query: str) -> dict:
    if not TAVILY_API_KEY:
        return {
            "mock": True,
            "query": query,
            "results": [
                {
                    "title": "[MOCK] Tavily result unavailable - no TAVILY_API_KEY set",
                    "url": "https://example.invalid/mock",
                    "content": f"This is a placeholder search result for '{query}'. "
                    "Set TAVILY_API_KEY to enable real web search.",
                }
            ],
        }

    # TODO(tavily): real call
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query},
        timeout=15.0,
    )
    resp.raise_for_status()
    return {"mock": False, "query": query, "results": resp.json().get("results", [])}
