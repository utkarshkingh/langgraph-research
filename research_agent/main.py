"""Research agent as an A2A service (FastAPI).

Two operations, both behind the same bearer auth as the gateway:
  POST /a2a/gather    -> runs the ReAct loop, returns INPUT_REQUIRED + proposed
  POST /a2a/finalize  -> validates human-approved assumptions, returns COMPLETED
  GET  /health        -> unauthenticated liveness

The service is stateless per call; durable run state lives in the orchestrator.
Run:  uvicorn research_agent.main:app --port 8081
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from common.security import verify_bearer
from research_agent import graph
from research_agent.schemas import (
    FinalizeRequest,
    FinalizeResponse,
    GatherRequest,
    GatherResponse,
    TaskState,
)

app = FastAPI(title="research-agent (A2A)")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/a2a/gather", response_model=GatherResponse)
def a2a_gather(req: GatherRequest, _=Depends(verify_bearer)) -> GatherResponse:
    proposed = graph.gather(req.query)
    # We always ask for human approval before finalizing -> INPUT_REQUIRED.
    return GatherResponse(
        state=TaskState.INPUT_REQUIRED,
        proposed=proposed,
        note="approve, override, or edit the proposed assumptions",
    )


@app.post("/a2a/finalize", response_model=FinalizeResponse)
def a2a_finalize(req: FinalizeRequest, _=Depends(verify_bearer)) -> FinalizeResponse:
    try:
        variables = graph.finalize(req.query, req.approved)
    except ValueError as e:
        # validation failure (e.g. low<=base<=high) is a client error, not a crash
        raise HTTPException(400, str(e)) from e
    return FinalizeResponse(state=TaskState.COMPLETED, variables=variables)
