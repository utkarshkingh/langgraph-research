"""The research agent: a ReAct loop, then a human review.

    START -> agent <-> tools          ReAct: the LLM picks tools until it has enough
               |
               v
            propose                    code turns tool results into assumptions
               |
               v
            review  <--+               interrupt(): pause and ask the human to approve
               |       | invalid       (loops back with the error until the answer is valid)
               v       |
              END -----+

The pause is saved by the checkpointer, so the human can answer much later.
"""
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt

from research_agent.llm import build_llm
from research_agent.tools import TOOLS

SYSTEM_PROMPT = (
    "You are a market researcher. Use web_search and statista_lookup to find "
    "low/base/high figures for the request. Stop when you have them."
)

llm = build_llm()


class ResearchState(MessagesState):   # MessagesState gives us `messages`
    request: str
    proposed: list[dict]               # assumptions waiting for review
    error: str | None                  # why the last answer was rejected
    result: dict                       # final output, read by the A2A executor


def agent(state: ResearchState) -> dict:
    """Ask the LLM what to do next: call a tool, or stop."""
    first_turn = [] if state["messages"] else [HumanMessage(state["request"])]
    messages = [SystemMessage(SYSTEM_PROMPT), *first_turn, *state["messages"]]
    response = llm.invoke(messages)
    return {"messages": [*first_turn, response]}


def propose(state: ResearchState) -> dict:
    """Copy every low/base/high figure out of the tool results. Code, not the LLM."""
    proposed = []
    for message in state["messages"]:
        if not isinstance(message, ToolMessage):
            continue
        output = json.loads(message.content)
        for item in output if isinstance(output, list) else [output]:
            if {"low", "base", "high"} <= item.keys():
                proposed.append({
                    "name": item["metric"],
                    "low": item["low"], "base": item["base"], "high": item["high"],
                    "source": item["source"],
                    # web figures are primary evidence; the data provider corroborates
                    "source_status": "research_value" if message.name == "web_search"
                                     else "support_range",
                })
    if not proposed:   # nothing usable found: say so instead of hiding it
        proposed.append({"name": "estimate", "low": 1, "base": 2, "high": 3,
                         "source": None, "source_status": "heuristic_fallback"})
    return {"proposed": proposed, "error": None}


def review(state: ResearchState) -> dict:
    """Human in the loop. interrupt() pauses here; the human's answer comes back as `answer`."""
    answer = interrupt({
        "question": "Reply 'approve', or send {'approved': [...]} with your edits.",
        "proposed": state["proposed"],
        "error": state["error"],
    })
    if answer == "approve":
        rows = state["proposed"]
    elif isinstance(answer, dict) and "approved" in answer:
        rows = answer["approved"]
    else:
        return {"error": "Reply 'approve' or send {'approved': [...]}."}

    error = check_ranges(rows)
    if error:
        return {"error": error}               # route() sends us back to review
    return {"error": None, "result": {"approved": rows}}


def check_ranges(rows: list[dict]) -> str | None:
    """Every assumption must satisfy low <= base <= high."""
    for row in rows:
        if not row["low"] <= row["base"] <= row["high"]:
            return f"'{row['name']}' breaks low <= base <= high"
    return None


def route(state: ResearchState) -> str:
    return "review" if state["error"] else END


def build_graph(checkpointer):
    graph = StateGraph(ResearchState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("propose", propose)
    graph.add_node("review", review)

    graph.add_edge(START, "agent")
    # tools_condition: "tools" if the LLM asked for a tool, otherwise END -> we go to propose
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "propose"})
    graph.add_edge("tools", "agent")
    graph.add_edge("propose", "review")
    graph.add_conditional_edges("review", route, ["review", END])
    return graph.compile(checkpointer=checkpointer)   # checkpointer = pause/resume
