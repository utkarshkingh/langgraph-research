"""The research agent's A2A contract: what it accepts and what it returns.

The research agent owns this file. Callers (the orchestrator) use it to build
requests and read responses, the way a client uses a service's published API.

This is a deliberately small, readable take on the A2A protocol's core idea: a task
has a lifecycle, and one of its states is INPUT_REQUIRED — the agent is telling the
caller "I need a human decision before I can finish." That single state is what makes
durable human-in-the-loop possible across a service boundary.

Real A2A has richer envelopes (Message / Part / Artifact, streaming via SSE). We keep
two operations and the states that matter for this pattern.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskState(str, Enum):
    COMPLETED = "completed"
    INPUT_REQUIRED = "input_required"   # the HITL signal
    FAILED = "failed"


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
