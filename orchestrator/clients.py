"""Pick how the orchestrator reaches the research agent.

  RESEARCH_MODE=inproc -> call the research graph in this process (simplest demo / tests)
  RESEARCH_MODE=http   -> real A2A hop over HTTP, with the service token attached

Both satisfy the same ResearchClient protocol, so graph.py doesn't care which is live.
"""
from __future__ import annotations

from common.a2a import (
    FinalizeRequest,
    FinalizeResponse,
    GatherRequest,
    GatherResponse,
    HttpResearchClient,
    ResearchClient,
    TaskState,
    ValidationRejected,
)
from common.config import settings


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
