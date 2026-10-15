"""The research agent's contract: what it accepts and what it returns.

The research agent owns this file. Callers (the orchestrator) use it to build
requests and read responses, the way a client uses a service's published API.

The transport is the A2A protocol (agent card, JSON-RPC SendMessage, tasks). These
models are the payload that travels inside the A2A messages, as a data part:

    gather    message 1 carries GatherRequest   -> task state INPUT_REQUIRED, proposed
    finalize  message 2 (same task id) carries
              FinalizeRequest                   -> task state COMPLETED, variables
                                                   (or INPUT_REQUIRED again + error)

INPUT_REQUIRED is the agent telling the caller "I need a human decision before I can
finish." That single state is what makes durable human-in-the-loop possible across a
service boundary.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskState(str, Enum):
    """The A2A task states this agent uses (TASK_STATE_* in the protocol)."""

    COMPLETED = "completed"
    INPUT_REQUIRED = "input_required"   # the HITL signal
    FAILED = "failed"


class GatherRequest(BaseModel):
    query: str


class GatherResponse(BaseModel):
    task_id: str = ""                    # the A2A task; send it back on finalize
    state: TaskState
    # when INPUT_REQUIRED: the assumptions the human must approve/override
    proposed: list[dict[str, Any]] = []
    note: str = ""


class FinalizeRequest(BaseModel):
    task_id: str = ""                    # continue the same A2A task
    query: str
    approved: list[dict[str, Any]]      # the human-approved assumptions


class FinalizeResponse(BaseModel):
    state: TaskState
    variables: list[dict[str, Any]] = []
    note: str = ""
