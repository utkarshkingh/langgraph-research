"""Calls another A2A agent: send one message, get back the task.

Used by the orchestrator to call the research agent, and by demo.py to call
the orchestrator. It speaks plain A2A, so it works with any A2A agent.
"""
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, new_data_part, new_text_part
from a2a.types import Message, Role, SendMessageRequest, TaskState


@dataclass
class TaskResult:
    task_id: str
    context_id: str
    state: str       # "TASK_STATE_INPUT_REQUIRED", "TASK_STATE_COMPLETED", ...
    data: dict       # the question (input required) or the result (completed)


async def send_message(agent_url: str, token: str, content: Any,
                       task_id: str = "", context_id: str = "") -> TaskResult:
    """Send `content` (text or a dict). Pass task_id/context_id to answer a paused task."""
    part = new_data_part(content) if isinstance(content, dict) else new_text_part(content)
    message = Message(message_id=str(uuid4()), role=Role.ROLE_USER, parts=[part],
                      task_id=task_id, context_id=context_id)

    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"},
                                 timeout=120) as http:
        # Reads the agent card at /.well-known/agent-card.json to find the endpoint.
        client = await create_client(agent_url, ClientConfig(httpx_client=http, streaming=False))
        async for response in client.send_message(SendMessageRequest(message=message)):
            task = response.task

    if task.status.state == TaskState.TASK_STATE_COMPLETED:
        data = get_data_parts(task.artifacts[0].parts)[0]
    else:
        data = (get_data_parts(task.status.message.parts) or [{}])[0]
    return TaskResult(task.id, task.context_id, TaskState.Name(task.status.state), data)
