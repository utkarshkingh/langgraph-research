"""State for the research agent's inner ReAct graph."""
from __future__ import annotations

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    query: str
    plan: list[str]
    evidence: list[dict[str, Any]]      # [{tool, args, result}] — the observe log
    pending: dict[str, Any] | None      # the next tool call the agent chose
    proposed: list[dict[str, Any]]      # assumptions with source_status
