"""Checkpointer factory.

The checkpointer is *the* reason human-in-the-loop can be durable. When the graph
hits interrupt(), LangGraph saves the full run state under the thread_id. The process
can be recycled, the user can walk away overnight; on resume we load the checkpoint
and continue exactly where we paused.

Local demo  -> SQLite (a file; zero setup).
Production   -> Postgres (shared, survives container restarts, handles concurrency).

Both are just LangGraph `BaseCheckpointSaver`s — the graph code doesn't change.
"""
from __future__ import annotations

import sqlite3

from common.config import settings


def build_checkpointer():
    if settings.checkpoint_backend == "postgres":
        # production path — requires the `azure` extra (langgraph-checkpoint-postgres)
        from langgraph.checkpoint.postgres import PostgresSaver  # pragma: no cover

        saver = PostgresSaver.from_conn_string(settings.postgres_dsn)
        saver.setup()
        return saver

    # local path — SQLite
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver
