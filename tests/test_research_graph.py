"""The research graph on its own: ReAct loop, pause, validation, resume."""
import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from common.config import settings
from research_agent.graph import build_graph, check_ranges
from research_agent.tools import statista_lookup

CONFIG = {"configurable": {"thread_id": "test-thread"}}


def run(graph, graph_input):
    return asyncio.run(graph.ainvoke(graph_input, CONFIG))


def test_pauses_for_review_then_resumes():
    graph = build_graph(InMemorySaver())

    paused = run(graph, {"request": "EV charging"})
    question = paused["__interrupt__"][0].value
    assert {row["source_status"] for row in question["proposed"]} == {"research_value", "support_range"}

    done = run(graph, Command(resume="approve"))
    assert done["result"]["approved"] == question["proposed"]


def test_invalid_answer_asks_again():
    graph = build_graph(InMemorySaver())
    proposed = run(graph, {"request": "EV charging"})["__interrupt__"][0].value["proposed"]

    bad = [{**proposed[0], "low": 99_000_000}]
    again = run(graph, Command(resume={"approved": bad}))
    assert "low <= base <= high" in again["__interrupt__"][0].value["error"]

    done = run(graph, Command(resume={"approved": proposed}))
    assert "result" in done


def test_check_ranges():
    assert check_ranges([{"name": "x", "low": 1, "base": 2, "high": 3}]) is None
    assert check_ranges([{"name": "x", "low": 3, "base": 2, "high": 1}])


def test_statista_over_real_mcp(monkeypatch):
    """Starts mcp_server/statista_server.py and calls its tool over stdio."""
    pytest.importorskip("mcp")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    result = asyncio.run(statista_lookup.ainvoke({"topic": "EV charging"}))
    assert result["source"] == "statista: EV charging"
