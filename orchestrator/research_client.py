"""How the orchestrator reaches the research agent (the client side of A2A).

  RESEARCH_MODE=inproc -> call the research graph in this process (simplest demo / tests)
  RESEARCH_MODE=http   -> real A2A hop over HTTP, with the service token attached

Both satisfy the same ResearchClient protocol, so graph.py doesn't care which is live.
The request/response models come from the research agent's own contract
(research_agent/schemas.py): the agent defines its API, the orchestrator calls it.
"""
from __future__ import annotations

from typing import Protocol

import httpx

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
