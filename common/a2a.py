"""A2A (agent-to-agent) contract between the orchestrator and the research agent.

This is a deliberately small, readable take on the A2A protocol's core idea: a task
has a lifecycle, and one of its states is INPUT_REQUIRED — the agent is telling the
caller "I need a human decision before I can finish." That single state is what makes
durable human-in-the-loop possible across a service boundary.

Real A2A has richer envelopes (Message / Part / Artifact, streaming via SSE). We keep
two operations and the states that matter for this pattern.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from common.auth import auth_header


class TaskState(str, Enum):
    COMPLETED = "completed"
    INPUT_REQUIRED = "input_required"   # the HITL signal
    FAILED = "failed"


class ValidationRejected(Exception):
    """The research agent refused the approved assumptions (e.g. low > base).

    Both clients raise this one exception, so the orchestrator handles a rejection
    the same way whether the agent ran in-process or over HTTP.
    """


class GatherRequest(BaseModel):
    thread_id: str
    query: str


class GatherResponse(BaseModel):
    state: TaskState
    # when INPUT_REQUIRED: the assumptions the human must approve/override
    proposed: list[dict[str, Any]] = []
    note: str = ""


class FinalizeRequest(BaseModel):
    thread_id: str
    query: str
    approved: list[dict[str, Any]]      # the human-approved assumptions


class FinalizeResponse(BaseModel):
    state: TaskState
    variables: list[dict[str, Any]] = []
    note: str = ""


class ResearchClient(Protocol):
    """What the orchestrator depends on. Two implementations: in-process and HTTP."""

    def gather(self, req: GatherRequest) -> GatherResponse: ...
    def finalize(self, req: FinalizeRequest) -> FinalizeResponse: ...


class HttpResearchClient:
    """Calls the research agent over HTTP, attaching a service-to-service token.

    This is the real A2A hop: a network call, authenticated with the orchestrator's
    own identity (managed identity in prod, shared token in dev).
    """

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def gather(self, req: GatherRequest) -> GatherResponse:
        r = httpx.post(
            f"{self._base}/a2a/gather",
            json=req.model_dump(),
            headers=auth_header(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        return GatherResponse(**r.json())

    def finalize(self, req: FinalizeRequest) -> FinalizeResponse:
        r = httpx.post(
            f"{self._base}/a2a/finalize",
            json=req.model_dump(),
            headers=auth_header(),
            timeout=self._timeout,
        )
        if r.status_code == 400:
            # the agent's validation said no: a business outcome, not a crash
            raise ValidationRejected(r.json().get("detail", "validation failed"))
        r.raise_for_status()
        return FinalizeResponse(**r.json())
