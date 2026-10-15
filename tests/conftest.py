"""Tests run offline: scripted model, mock search, SQLite, in-process agent.

The real defaults (LiteLLM, Tavily, Postgres, HTTP) are switched off here, before
`common.config` is imported, so no keys or database are needed.
"""
import os

os.environ.update(
    MODEL_BACKEND="scripted",
    SEARCH_BACKEND="mock",
    MCP_ENABLED="false",
    CHECKPOINT_BACKEND="sqlite",
    SQLITE_PATH=":memory:",
    RESEARCH_MODE="inproc",
)
