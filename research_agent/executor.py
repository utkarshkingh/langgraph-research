"""The bridge between the A2A protocol and the research agent's functions.

The A2A server calls execute() for every incoming message. This class does not
contain any research logic: it calls graph.gather() and graph.finalize() (unchanged)
and reports how they ended as an A2A task state.

    message 1 (no task yet)   gather()    -> TASK_STATE_INPUT_REQUIRED + proposed assumptions
    message 2 (same task id)  finalize()  -> TASK_STATE_COMPLETED      + variables artifact
                                             or INPUT_REQUIRED again   + the validation error

One A2A task = one research request. The task stays open (input-required) while the
orchestrator waits for the human, so the task store keeps it between the two messages.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from a2a.helpers import (
    get_data_parts,
    new_data_part,
    new_task_from_user_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Message
from a2a.utils.errors import UnsupportedOperationError

from research_agent import graph

logger = logging.getLogger(__name__)


class ResearchExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # First message creates the task; the answer to a paused task reuses it.
        first = context.current_task is None
        task = context.current_task or new_task_from_user_message(context.message)
        if first:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        data = read_data(context.message)
        try:
            if first:
                await self._gather(updater, data)
            else:
                await self._finalize(updater, data)
        except Exception:
            logger.exception("research task failed")
            await updater.failed(updater.new_agent_message([new_text_part("Request failed.")]))

    async def _gather(self, updater: TaskUpdater, data: dict[str, Any]) -> None:
        # The ReAct loop is blocking code, so run it in a worker thread.
        proposed = await asyncio.to_thread(graph.gather, data["query"])
        # We always ask for human approval before finalizing -> INPUT_REQUIRED.
        await updater.requires_input(
            updater.new_agent_message([
                new_text_part("approve, override, or edit the proposed assumptions"),
                new_data_part({"proposed": proposed}),
            ])
        )

    async def _finalize(self, updater: TaskUpdater, data: dict[str, Any]) -> None:
        try:
            variables = await asyncio.to_thread(graph.finalize, data["query"], data["approved"])
        except ValueError as e:
            # Validation said no (e.g. low<=base<=high): a business outcome, not a crash.
            # The task goes back to input-required, carrying the reason.
            await updater.requires_input(
                updater.new_agent_message([new_text_part(str(e)), new_data_part({"error": str(e)})])
            )
            return
        await updater.add_artifact([new_data_part({"variables": variables})], name="variables")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError("Cancel is not supported")


def read_data(message: Message) -> dict[str, Any]:
    """The JSON the caller sent (the data part of the message)."""
    parts = get_data_parts(message.parts)
    return parts[0] if parts else {}
