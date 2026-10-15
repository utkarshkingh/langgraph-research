"""Web search tool for the ReAct loop.

Pluggable backend so the demo runs offline:
  SEARCH_BACKEND=mock   -> canned, deterministic snippets (no network, no key)
  SEARCH_BACKEND=tavily -> real search via Tavily (needs TAVILY_API_KEY)

The important interview point is not which provider we use but how the *output* is
treated: search results are UNTRUSTED content. They become evidence with a source
tag; they never drive control flow, and any number is range-checked before it is
allowed into a result. See graph.py (propose) and finalize().
"""
from __future__ import annotations

from typing import Any

from common.config import settings

# Deterministic canned corpus for the offline demo.
_MOCK_CORPUS: dict[str, list[dict[str, Any]]] = {
    "default": [
        {
            "title": "Industry outlook 2026 (mock)",
            "url": "https://example.com/outlook",
            "snippet": "The addressable base is estimated at roughly 12 million units, "
            "with analysts citing a plausible range of 10-14 million.",
            "value_hint": {"base": 12_000_000, "low": 10_000_000, "high": 14_000_000},
        },
        {
            "title": "Pricing survey (mock)",
            "url": "https://example.com/pricing",
            "snippet": "Average annual spend per unit clusters around EUR 180 "
            "(reported range EUR 150-210).",
            "value_hint": {"base": 180, "low": 150, "high": 210},
        },
    ]
}


def web_search(query: str, k: int = 2) -> list[dict[str, Any]]:
    if settings.search_backend == "tavily":
        return _tavily(query, k)
    return _MOCK_CORPUS["default"][:k]


def _tavily(query: str, k: int) -> list[dict[str, Any]]:  # pragma: no cover - needs key
    import httpx

    r = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": settings.tavily_api_key, "query": query, "max_results": k},
        timeout=30.0,
    )
    r.raise_for_status()
    return [
        {"title": x["title"], "url": x["url"], "snippet": x["content"], "value_hint": {}}
        for x in r.json().get("results", [])
    ]
