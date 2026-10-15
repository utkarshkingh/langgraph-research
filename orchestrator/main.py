"""Orchestrator gateway (FastAPI).

  POST /invoke  {request}             -> runs until the HITL pause; returns thread_id +
                                         the proposed assumptions to approve
  POST /resume  {thread_id, approved} -> resumes from the checkpoint; returns the report
  GET  /health                        -> unauthenticated liveness

Both POSTs are behind bearer auth (Depends(verify_bearer)). The endpoints are sync defs
so FastAPI runs them in a threadpool — convenient with the sync SQLite checkpointer.

Run:  uvicorn orchestrator.main:app --port 8080
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from common.auth import verify_bearer
from common.checkpoint import build_checkpointer
from orchestrator.graph import build_orchestrator

app = FastAPI(title="orchestrator-gateway")
_graph = build_orchestrator(build_checkpointer())


class InvokeIn(BaseModel):
    request: str
    thread_id: str


class ResumeIn(BaseModel):
    thread_id: str
    approved: list[dict[str, Any]]


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoke", dependencies=[Depends(verify_bearer)])
def invoke(body: InvokeIn) -> dict[str, Any]:
    result = _graph.invoke({"request": body.request}, config=_config(body.thread_id))

    # interrupt() surfaces here as __interrupt__ on the result.
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {
            "status": "input_required",
            "thread_id": body.thread_id,
            "proposed": payload["proposed"],
            "instructions": payload["instructions"],
        }
    return {"status": "completed", "report": result["report"]}


@app.post("/resume", dependencies=[Depends(verify_bearer)])
def resume(body: ResumeIn) -> dict[str, Any]:
    try:
        result = _graph.invoke(
            Command(resume={"approved": body.approved}), config=_config(body.thread_id)
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    if "__interrupt__" in result:
        raise HTTPException(409, "still awaiting input")
    return {"status": "completed", "report": result["report"]}
