"""How the orchestrator reaches the research agent (the client side of A2A).

  RESEARCH_MODE=inproc -> call the research graph in this process (simplest demo / tests)
  RESEARCH_MODE=http   -> real A2A hop (official a2a-sdk client) with the service token

Both satisfy the same ResearchClient protocol, so graph.py doesn't care which is live.
The request/response models come from the research agent's own contract
(research_agent/schemas.py): the agent defines its API, the orchestrator calls it.
"""
from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, new_data_part
from a2a.types import Message, Role, SendMessageRequest, Task, TaskState as A2ATaskState

from common.config import settings
from common.security import auth_header
from research_agent.schemas import (
    FinalizeRequest,
    FinalizeResponse,
    GatherRequest,
    GatherResponse,
    TaskState,
)


class ValidationRejected(Exception):
    """The research agent refused the approved assumptions (e.g. low > base).

    Both clients raise this one exception, so the orchestrator handles a rejection
    the same way whether the agent ran in-process or over HTTP.
    """


class ResearchClient(Protocol):
    """What the orchestrator depends on. Two implementations: in-process and HTTP."""

    def gather(self, req: GatherRequest) -> GatherResponse: ...
    def finalize(self, req: FinalizeRequest) -> FinalizeResponse: ...


class HttpResearchClient:
    """Calls the research agent over A2A, attaching a service-to-service token.

    This is the real A2A hop: the SDK client reads the agent card at
    /.well-known/agent-card.json, then sends JSON-RPC SendMessage calls. The caller
    is authenticated with the orchestrator's own identity (managed identity in prod,
    shared token in dev).

        gather    -> message 1 (new task)       -> task comes back INPUT_REQUIRED
        finalize  -> message 2 (same task id)   -> COMPLETED, or INPUT_REQUIRED + error
    """

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def gather(self, req: GatherRequest) -> GatherResponse:
        task = self._send({"query": req.query})
        if task.status.state != A2ATaskState.TASK_STATE_INPUT_REQUIRED:
            raise RuntimeError(f"research agent ended in {A2ATaskState.Name(task.status.state)}")
        data = _status_data(task)
        return GatherResponse(
            task_id=task.id,
            state=TaskState.INPUT_REQUIRED,
            proposed=data.get("proposed", []),
        )

    def finalize(self, req: FinalizeRequest) -> FinalizeResponse:
        task = self._send(
            {"query": req.query, "approved": req.approved}, task_id=req.task_id
        )
        if task.status.state == A2ATaskState.TASK_STATE_INPUT_REQUIRED:
            # the agent's validation said no: a business outcome, not a crash
            raise ValidationRejected(_status_data(task).get("error", "validation failed"))
        if task.status.state != A2ATaskState.TASK_STATE_COMPLETED:
            raise RuntimeError(f"research agent ended in {A2ATaskState.Name(task.status.state)}")
        variables = get_data_parts(task.artifacts[0].parts)[0]["variables"]
        return FinalizeResponse(state=TaskState.COMPLETED, variables=variables)

    def _send(self, content: dict[str, Any], task_id: str = "") -> Task:
        """Send one A2A message and return the task. (Sync wrapper: the graph nodes are sync.)"""
        return asyncio.run(self._send_async(content, task_id, auth_header()))

    async def _send_async(self, content: dict[str, Any], task_id: str, headers: dict) -> Task:
        message = Message(
            message_id=str(uuid4()), role=Role.ROLE_USER,
            parts=[new_data_part(content)], task_id=task_id,
        )
        task = None
        async with httpx.AsyncClient(headers=headers, timeout=self._timeout) as http:
            client = await create_client(self._base, ClientConfig(httpx_client=http, streaming=False))
            async for response in client.send_message(SendMessageRequest(message=message)):
                task = response.task
        if task is None:
            raise RuntimeError("research agent returned no task")
        return task


def _status_data(task: Task) -> dict[str, Any]:
    """The JSON the agent attached to the task's status message."""
    return (get_data_parts(task.status.message.parts) or [{}])[0]


class InProcResearchClient:
    """Calls the research agent's functions directly — no network, no auth."""

    def gather(self, req: GatherRequest) -> GatherResponse:
        from research_agent import graph

        proposed = graph.gather(req.query)
        return GatherResponse(state=TaskState.INPUT_REQUIRED, proposed=proposed)

    def finalize(self, req: FinalizeRequest) -> FinalizeResponse:
        from research_agent import graph

        try:
            variables = graph.finalize(req.query, req.approved)
        except ValueError as e:
            raise ValidationRejected(str(e)) from e
        return FinalizeResponse(state=TaskState.COMPLETED, variables=variables)


def get_research_client() -> ResearchClient:
    if settings.research_mode == "http":
        return HttpResearchClient(settings.research_agent_url)
    return InProcResearchClient()
