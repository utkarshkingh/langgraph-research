"""The orchestrator: calls the research agent over A2A and relays its questions to the user.

    START -> call_research --input required--> human_review --+
                 ^                                            |
                 +--------------------------------------------+
                 |
                 +--completed--> report -> END
                 +--failed-----> END  (the A2A task fails)

When the research agent pauses (TASK_STATE_INPUT_REQUIRED), the orchestrator
pauses too, with interrupt(), and shows the user the same question. The user's
answer is sent back to the research agent on the SAME task id, which resumes it.
Both services checkpoint their own state.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from common.config import settings
from common.security import get_outgoing_token
from orchestrator.a2a_client import send_message


class OrchestratorState(TypedDict, total=False):
    request: str
    research_task_id: str
    research_context_id: str
    research_state: str     # A2A task state of the research agent's task
    research_data: dict     # its question, or its result
    human_answer: Any
    result: dict            # final output, read by the A2A executor


async def call_research(state: OrchestratorState) -> dict:
    """A2A call. First time: send the request. After a pause: send the human's answer."""
    token = await get_outgoing_token()
    if state.get("research_task_id"):
        task = await send_message(settings.research_agent_url, token, state["human_answer"],
                                  state["research_task_id"], state["research_context_id"])
    else:
        task = await send_message(settings.research_agent_url, token, state["request"])
    return {
        "research_task_id": task.task_id,
        "research_context_id": task.context_id,
        "research_state": task.state,
        "research_data": task.data,
    }


def human_review(state: OrchestratorState) -> dict:
    """Pause and pass the research agent's question up to the user."""
    answer = interrupt(state["research_data"])
    return {"human_answer": answer}


def report(state: OrchestratorState) -> dict:
    """Write the final report. Every number keeps its source status."""
    lines = [f"Market sizing: {state['request']}"]
    for row in state["research_data"]["approved"]:
        lines.append(f"- {row['name']}: {row['base']:,.0f} "
                     f"(low {row['low']:,.0f}, high {row['high']:,.0f}) [{row['source_status']}]")
    return {"result": {"report": "\n".join(lines)}}


def route(state: OrchestratorState) -> str:
    if state["research_state"] == "TASK_STATE_INPUT_REQUIRED":
        return "human_review"
    if state["research_state"] == "TASK_STATE_COMPLETED":
        return "report"
    return END


def build_graph(checkpointer):
    graph = StateGraph(OrchestratorState)
    graph.add_node("call_research", call_research)
    graph.add_node("human_review", human_review)
    graph.add_node("report", report)

    graph.add_edge(START, "call_research")
    graph.add_conditional_edges("call_research", route, ["human_review", "report", END])
    graph.add_edge("human_review", "call_research")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
