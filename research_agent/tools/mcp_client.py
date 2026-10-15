"""Statista-style structured-data tool, reached over MCP.

This shows the real MCP *client* wiring: we spawn an MCP server over stdio, open a
session, and call one of its advertised tools. The server lives in mcp_server/ and
is a tiny FastMCP app.

MCP_ENABLED=false (the default) short-circuits to the same canned data the server
would return, so the offline demo has zero moving parts. Flip MCP_ENABLED=true (with
the `mcp` extra installed) to exercise the actual stdio transport.
"""
from __future__ import annotations

import os
import sys
from typing import Any

from common.config import settings

_SERVER = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server", "statista_stub.py")

# Canned fallback — identical in shape to what the MCP tool returns.
_CANNED: dict[str, Any] = {
    "topic": "default",
    "base": 11_500_000,
    "low": 10_500_000,
    "high": 13_000_000,
    "historical_cagr": 0.06,
    "source": "statista-stub",
}


def statista_lookup(topic: str) -> dict[str, Any]:
    if not settings.mcp_enabled:
        return {**_CANNED, "topic": topic}
    return _lookup_over_mcp(topic)  # pragma: no cover - needs mcp extra + subprocess


def _lookup_over_mcp(topic: str) -> dict[str, Any]:  # pragma: no cover
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run() -> dict[str, Any]:
        params = StdioServerParameters(command=sys.executable, args=[_SERVER])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("statista_lookup", {"topic": topic})
                # FastMCP returns structured content; take the first text/JSON part.
                return result.structuredContent or _CANNED

    return asyncio.run(_run())
