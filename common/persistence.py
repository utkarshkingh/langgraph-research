"""Where each service keeps its state.

Two stores, both chosen by POSTGRES_DSN:

    LangGraph checkpointer  the graph's state, saved after every node.
                            This is what makes pause/resume survive a restart.
    A2A task store          the A2A tasks (id, state, messages, artifacts).

Local (no DSN):  both in memory. Production: both in Postgres, so any replica
can pick up any paused task. Each service has its own database.
"""
from contextlib import asynccontextmanager

from a2a.server.tasks import DatabaseTaskStore, InMemoryTaskStore, TaskStore
from langgraph.checkpoint.memory import InMemorySaver

from common.config import settings


@asynccontextmanager
async def open_checkpointer():
    """Open the checkpointer for the lifetime of the app."""
    if not settings.postgres_dsn:
        yield InMemorySaver()
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(settings.postgres_dsn) as saver:
        await saver.setup()  # creates the checkpoint tables if they don't exist
        yield saver


def create_task_store() -> TaskStore:
    if not settings.postgres_dsn:
        return InMemoryTaskStore()

    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = settings.postgres_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return DatabaseTaskStore(create_async_engine(dsn), create_table=True)
