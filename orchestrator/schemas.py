"""Request bodies for the orchestrator's gateway API (POST /invoke, POST /resume)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class InvokeRequest(BaseModel):
    request: str
    thread_id: str


class ResumeRequest(BaseModel):
    thread_id: str
    approved: list[dict[str, Any]]
