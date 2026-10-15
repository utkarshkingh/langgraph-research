"""The research agent's inner graph — a ReAct loop drawn as explicit LangGraph nodes.

    plan ──> agent ──(tool?)──> tools ──┐
                 │                       │
                 └────(done?)──> propose ┘ ──> END
                                   (loop: tools ──> agent)

This is the 'what does the agent code actually look like' artifact. Four named nodes,
one conditional edge. The model behind `agent` is swappable (scripted / Azure OpenAI).

Note on human-in-the-loop placement: the PAUSE lives in the orchestrator graph, not
here. This graph runs to a proposal and returns; the orchestrator interrupts for human
approval, then calls finalize(). Keeping the agent side stateless-per-call makes the
A2A contract simple and the durable state single-sourced in the orchestrator.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from research_agent.model import build_model
from research_agent.tools.mcp_client import statista_lookup
from research_agent.tools.web_search import web_search


class ResearchState(TypedDict, total=False):
    """State for the research agent's inner ReAct graph."""

    query: str
    plan: list[str]
    evidence: list[dict[str, Any]]      # [{tool, args, result}] — the observe log
    pending: dict[str, Any] | None      # the next tool call the agent chose
    proposed: list[dict[str, Any]]      # assumptions with source_status

_model = build_model()

_TOOLS = {
    "web_search": lambda args: web_search(args.get("query", "")),
    "statista_lookup": lambda args: statista_lookup(args.get("topic", "")),
}


def plan_node(state: ResearchState) -> dict[str, Any]:
    """Cheap, explicit plan. In prod this can be an LLM call; here it is fixed."""
    return {
        "plan": [
            "find a demand-side base estimate and range",
            "corroborate with structured data (Statista via MCP)",
            "propose assumptions, each tagged with a source status",
        ],
        "evidence": [],
        "pending": None,
    }


def agent_node(state: ResearchState) -> dict[str, Any]:
    """Reason: pick the next tool, or decide we have enough to propose."""
    decision = _model.decide(state["query"], state.get("evidence", []))
    if decision.action == "tool":
        return {"pending": {"tool": decision.tool, "args": decision.args}}
    return {"pending": None, "proposed": decision.proposed}


def tools_node(state: ResearchState) -> dict[str, Any]:
    """Act + observe: run the chosen tool, append to the evidence log."""
    call = state["pending"]
    tool = call["tool"]
    result = _TOOLS[tool](call["args"])
    evidence = list(state.get("evidence", []))
    evidence.append({"tool": tool, "args": call["args"], "result": result})
    return {"evidence": evidence, "pending": None}


def propose_node(state: ResearchState) -> dict[str, Any]:
    """Pass-through: the model attached `proposed` on finish. Here we could enrich."""
    return {"proposed": state.get("proposed", [])}


def _route(state: ResearchState) -> str:
    return "tools" if state.get("pending") else "propose"


def build_gather_graph():
    g = StateGraph(ResearchState)
    g.add_node("plan", plan_node)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("propose", propose_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "agent")
    g.add_conditional_edges("agent", _route, {"tools": "tools", "propose": "propose"})
    g.add_edge("tools", "agent")       # the ReAct loop
    g.add_edge("propose", END)
    return g.compile()                 # no checkpointer: one call runs to a proposal


_gather = build_gather_graph()


# --------------------------------------------------------------------------- #
# Public operations used by the A2A service (main.py) and the in-process client
# --------------------------------------------------------------------------- #
def gather(query: str) -> list[dict[str, Any]]:
    """Run the ReAct loop, return proposed assumptions (each with a source_status)."""
    out = _gather.invoke({"query": query})
    return out["proposed"]


def finalize(query: str, approved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the human-approved assumptions: enforce low <= base <= high.

    This is the guardrail that lets LLM-sourced numbers be trusted downstream.
    A violation is a hard error, not a silent clamp.
    """
    validated: list[dict[str, Any]] = []
    for a in approved:
        low, base, high = a["low"], a["base"], a["high"]
        if not (low <= base <= high):
            raise ValueError(
                f"assumption '{a.get('name')}' violates low<=base<=high: {low},{base},{high}"
            )
        validated.append({**a, "validated": True})
    return validated
