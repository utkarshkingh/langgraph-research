"""In-process smoke test: proves the pause/resume works and validation bites.

Runs with no network, no keys (scripted model, mock search, MCP disabled).
    pytest -q
"""
from __future__ import annotations

import uuid

import pytest
from langgraph.types import Command

from common.checkpoint import build_checkpointer
from orchestrator.graph import build_orchestrator
from research_agent import graph as research


def _graph():
    return build_orchestrator(build_checkpointer())


def test_pause_then_resume_produces_report():
    g = _graph()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}

    first = g.invoke({"request": "Size the EU EV charging aftermarket"}, config=cfg)
    assert "__interrupt__" in first, "run should pause for human approval"

    proposed = first["__interrupt__"][0].value["proposed"]
    assert proposed and all("source_status" in p for p in proposed)

    final = g.invoke(Command(resume={"approved": proposed}), config=cfg)
    assert "__interrupt__" not in final
    assert "Market sizing:" in final["report"]
    assert "source=" in final["report"]


def test_react_loop_uses_both_tools():
    proposed = research.gather("anything")
    # scripted policy must have exercised web_search then statista_lookup
    assert proposed, "expected at least one proposed assumption"


def test_finalize_rejects_bad_band():
    with pytest.raises(ValueError):
        research.finalize("q", [{"name": "x", "low": 10, "base": 5, "high": 20}])
