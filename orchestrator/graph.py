"""The outer orchestrator graph — where durable human-in-the-loop lives.

    intake ──> research_gather ──> await_market_input ──> research_finalize ──> report ──> END
                  (A2A call)         (interrupt + pause)      (A2A call)  │
                                            ▲                             │
                                            └──── rejected by validation ─┘

`await_market_input` calls LangGraph's interrupt(): the run pauses and the state is
written to the checkpointer under the thread_id. The process can be recycled; the user
can approve later. On resume (Command(resume=...)) the graph continues from the saved
checkpoint with the human's decision in hand.

If the research agent's validation rejects what the human sent (e.g. low > base), the
graph loops back to the pause and shows the error, so the human can fix it and resume
again. The run never gets stuck on a bad answer.

This is the whole point of the pattern: the pause is a checkpoint, not a held-open
request or a timeout.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from orchestrator.research_client import ValidationRejected, get_research_client
from research_agent.schemas import FinalizeRequest, GatherRequest

_research = get_research_client()


class OrchestratorState(TypedDict, total=False):
    """State for the orchestrator's outer graph."""

    request: str                         # the market scope to size
    proposed: list[dict[str, Any]]       # assumptions the research agent proposed
    approval: dict[str, Any]             # what the human returned on resume
    approval_error: str | None           # set when validation rejects the approval
    variables: list[dict[str, Any]]      # validated, approved assumptions
    report: str                          # final assembled memo


def intake_node(state: OrchestratorState) -> dict[str, Any]:
    """Normalize the incoming request. (Collapses the real entry routers/gates.)"""
    return {"request": state["request"].strip()}


def research_gather_node(state: OrchestratorState) -> dict[str, Any]:
    """A2A -> research agent. Comes back INPUT_REQUIRED with proposed assumptions."""
    resp = _research.gather(GatherRequest(thread_id="n/a", query=state["request"]))
    return {"proposed": resp.proposed}


def await_market_input_node(state: OrchestratorState) -> dict[str, Any]:
    """THE human-in-the-loop pause.

    interrupt(payload) surfaces the proposed assumptions to the caller and suspends the
    run. Whatever the human sends back via Command(resume=...) becomes `decision`.
    On a retry after a rejection, the payload also carries the validation error.
    """
    decision = interrupt(
        {
            "type": "approve_assumptions",
            "request": state["request"],
            "proposed": state["proposed"],
            "error": state.get("approval_error"),
            "instructions": "Return {'approved': [...]} — the assumptions to finalize.",
        }
    )
    return {"approval": decision}


def research_finalize_node(state: OrchestratorState) -> dict[str, Any]:
    """A2A -> research agent again, now with the approved assumptions. Validates."""
    approved = state["approval"].get("approved", state["proposed"])
    try:
        resp = _research.finalize(
            FinalizeRequest(thread_id="n/a", query=state["request"], approved=approved)
        )
    except ValidationRejected as e:
        # Keep the reason; the router below sends the run back to the pause.
        return {"approval_error": str(e)}
    return {"variables": resp.variables, "approval_error": None}


def _after_finalize(state: OrchestratorState) -> str:
    """Rejected -> ask the human again. Accepted -> write the report."""
    return "await_market_input" if state.get("approval_error") else "report"


def report_node(state: OrchestratorState) -> dict[str, Any]:
    """Assemble the memo. Every number keeps its source_status (provenance)."""
    lines = [f"Market sizing: {state['request']}", ""]
    for v in state["variables"]:
        lines.append(
            f"- {v['name']}: base={v['base']} (low={v['low']}, high={v['high']}) "
            f"[source={v['source_status']}]"
        )
    return {"report": "\n".join(lines)}


def build_orchestrator(checkpointer):
    g = StateGraph(OrchestratorState)
    g.add_node("intake", intake_node)
    g.add_node("research_gather", research_gather_node)
    g.add_node("await_market_input", await_market_input_node)
    g.add_node("research_finalize", research_finalize_node)
    g.add_node("report", report_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "research_gather")
    g.add_edge("research_gather", "await_market_input")
    g.add_edge("await_market_input", "research_finalize")
    g.add_conditional_edges(
        "research_finalize",
        _after_finalize,
        {"await_market_input": "await_market_input", "report": "report"},
    )
    g.add_edge("report", END)

    # A checkpointer is REQUIRED for interrupt()/resume to work.
    return g.compile(checkpointer=checkpointer)
