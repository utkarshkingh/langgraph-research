"""Checkpointer factory.

The checkpointer is *the* reason human-in-the-loop can be durable. When the graph
hits interrupt(), LangGraph saves the full run state under the thread_id. The process
can be recycled, the user can walk away overnight; on resume we load the checkpoint
and continue exactly where we paused.

Default      -> Postgres (shared, survives container restarts, handles concurrency).
Tests / offline demo -> SQLite (a file; CHECKPOINT_BACKEND=sqlite).

Both are just LangGraph `BaseCheckpointSaver`s — the graph code doesn't change.
"""
from __future__ import annotations

import sqlite3

from common.config import settings


def build_checkpointer():
    if settings.checkpoint_backend == "postgres":
        if not settings.postgres_dsn:
            raise ValueError(
                "POSTGRES_DSN is empty. Set it in .env (see .env.example), or "
                "CHECKPOINT_BACKEND=sqlite for the offline demo."
            )
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection

        # A long-lived connection for the life of the app (from_conn_string is a
        # context manager, which would close the connection as soon as it returns).
        conn = Connection.connect(settings.postgres_dsn, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver

    # local path — SQLite
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver
