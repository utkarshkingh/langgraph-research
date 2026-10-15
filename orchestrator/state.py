"""State for the orchestrator's outer graph."""
from __future__ import annotations

from typing import Any, TypedDict


class OrchestratorState(TypedDict, total=False):
    request: str                         # the market scope to size
    proposed: list[dict[str, Any]]       # assumptions the research agent proposed
    approval: dict[str, Any]             # what the human returned on resume
    variables: list[dict[str, Any]]      # validated, approved assumptions
    report: str                          # final assembled memo
