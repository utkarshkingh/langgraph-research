"""Orchestrator gateway (FastAPI).

  POST /invoke  {request, thread_id}  -> runs until the HITL pause; returns thread_id +
                                         the proposed assumptions to approve
  POST /resume  {thread_id, approved} -> resumes from the checkpoint; returns the report,
                                         or input_required again (with the error) if
                                         validation rejected the approval
  GET  /health                        -> unauthenticated liveness

Both POSTs are behind bearer auth (Depends(verify_bearer)). The endpoints are sync defs
so FastAPI runs them in a threadpool — convenient with the sync SQLite checkpointer.

Run:  uvicorn orchestrator.main:app --port 8080
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from langgraph.types import Command

from common.checkpointer import build_checkpointer
from common.security import verify_bearer
from orchestrator.graph import build_orchestrator
from orchestrator.schemas import InvokeRequest, ResumeRequest

app = FastAPI(title="orchestrator-gateway")
_graph = build_orchestrator(build_checkpointer())


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _respond(result: dict, thread_id: str) -> dict[str, Any]:
    """Turn a graph result into the API response: paused or finished."""
    # interrupt() surfaces here as __interrupt__ on the result.
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {
            "status": "input_required",
            "thread_id": thread_id,
            "proposed": payload["proposed"],
            "error": payload.get("error"),
            "instructions": payload["instructions"],
        }
    return {"status": "completed", "report": result["report"]}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoke", dependencies=[Depends(verify_bearer)])
def invoke(body: InvokeRequest) -> dict[str, Any]:
    result = _graph.invoke({"request": body.request}, config=_config(body.thread_id))
    return _respond(result, body.thread_id)


@app.post("/resume", dependencies=[Depends(verify_bearer)])
def resume(body: ResumeRequest) -> dict[str, Any]:
    try:
        result = _graph.invoke(
            Command(resume={"approved": body.approved}), config=_config(body.thread_id)
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return _respond(result, body.thread_id)
