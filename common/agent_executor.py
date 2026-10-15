"""The bridge between A2A and LangGraph. Used by both services.

The A2A server calls execute() for every incoming message. We run the graph
and translate how it ended into an A2A task state:

    graph paused at interrupt()   ->  TASK_STATE_INPUT_REQUIRED  (+ the question)
    graph wrote state["result"]   ->  TASK_STATE_COMPLETED       (+ result artifact)
    anything else / exception     ->  TASK_STATE_FAILED

One A2A task = one graph thread (thread_id = task id). When the caller answers
an input-required task, it sends a message with the same task id, and we resume
the paused graph with Command(resume=answer).
"""
import logging

from a2a.helpers import get_data_parts, get_message_text, new_data_part, new_text_part
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Message
from a2a.utils.errors import UnsupportedOperationError
from langgraph.types import Command

logger = logging.getLogger(__name__)


class LangGraphAgentExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.graph = None  # set at startup, once the checkpointer is open (common/server.py)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # New request -> create the task. Answer to a paused task -> reuse it.
        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        config = {"configurable": {"thread_id": task.id}}
        user_input = read_user_input(context.message)
        snapshot = await self.graph.aget_state(config)
        graph_input = Command(resume=user_input) if snapshot.next else {"request": user_input}

        try:
            await self.graph.ainvoke(graph_input, config)
        except Exception:
            logger.exception("graph run failed")
            await updater.failed(updater.new_agent_message([new_text_part("Request failed.")]))
            return

        snapshot = await self.graph.aget_state(config)
        if snapshot.interrupts:                      # paused: ask the caller
            question = snapshot.interrupts[0].value
            parts = [new_text_part(question["question"]), new_data_part(question)]
            await updater.requires_input(updater.new_agent_message(parts))
        elif "result" in snapshot.values:            # finished
            await updater.add_artifact([new_data_part(snapshot.values["result"])], name="result")
            await updater.complete()
        else:
            await updater.failed(updater.new_agent_message([new_text_part("No result.")]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError("Cancel is not supported")


def read_user_input(message: Message):
    """A data part (JSON) if the caller sent one, otherwise the text."""
    data = get_data_parts(message.parts)
    return data[0] if data else get_message_text(message).strip()
