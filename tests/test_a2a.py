"""The A2A hop for real: a live research-agent server, the orchestrator calling it over HTTP.

Offline like the other tests (scripted model, mock search, in-memory task store), but
the traffic between the two services is genuine A2A: agent card, JSON-RPC SendMessage,
bearer token, one task carried across both messages.
"""
from __future__ import annotations

import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn
from langgraph.types import Command

from common.checkpointer import build_checkpointer
from orchestrator import graph as orchestrator_graph
from orchestrator.research_client import HttpResearchClient


@pytest.fixture(scope="module")
def agent_url():
    from research_agent.main import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(create_app(url), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def orchestrator(agent_url, monkeypatch):
    """The real orchestrator graph, wired to the live agent over A2A."""
    monkeypatch.setattr(orchestrator_graph, "_research", HttpResearchClient(agent_url))
    return orchestrator_graph.build_orchestrator(build_checkpointer())


def test_agent_card_is_public(agent_url):
    card = httpx.get(f"{agent_url}/.well-known/agent-card.json").json()
    assert card["name"] == "Research Agent"
    assert card["skills"][0]["id"] == "research_market"


def test_a2a_endpoint_needs_a_token(agent_url):
    assert httpx.post(f"{agent_url}/", json={}).status_code == 401


def test_pause_resume_over_a2a(orchestrator):
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}

    first = orchestrator.invoke({"request": "Size the EU EV charging aftermarket"}, config=cfg)
    assert "__interrupt__" in first
    proposed = first["__interrupt__"][0].value["proposed"]
    assert proposed and all("source_status" in p for p in proposed)
    # the A2A task id was kept, so the answer goes back to the same task
    assert orchestrator.get_state(cfg).values["research_task_id"]

    final = orchestrator.invoke(Command(resume={"approved": proposed}), config=cfg)
    assert "__interrupt__" not in final
    assert "Market sizing:" in final["report"]


def test_validation_rejection_reprompts_over_a2a(orchestrator):
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}

    first = orchestrator.invoke({"request": "Size the EU EV charging aftermarket"}, config=cfg)
    good = first["__interrupt__"][0].value["proposed"]
    bad = [{"name": "x", "low": 9, "base": 1, "high": 2, "source_status": "research_value"}]

    # The agent sends the task back to input-required with the reason; the run pauses again.
    again = orchestrator.invoke(Command(resume={"approved": bad}), config=cfg)
    assert "low<=base<=high" in again["__interrupt__"][0].value["error"]

    # The corrected answer goes to the same task and completes it.
    final = orchestrator.invoke(Command(resume={"approved": good}), config=cfg)
    assert "Market sizing:" in final["report"]
