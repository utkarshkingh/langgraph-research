"""The research agent's two tools.

    web_search       open web results (mock offline, Tavily for real)
    statista_lookup  structured market data from an MCP server (mcp_server/)

Tool output is untrusted evidence: it never decides what the graph does next,
and every number is checked in graph.py before anyone can approve it.
"""
import json
import sys
from pathlib import Path

import httpx
from langchain_core.tools import tool

from common.config import settings

MCP_SERVER = Path(__file__).parent.parent / "mcp_server" / "statista_server.py"

MOCK_RESULTS = [
    {"metric": "installed_base_units", "low": 10_000_000, "base": 12_000_000, "high": 14_000_000,
     "source": "https://example.com/industry-outlook"},
    {"metric": "annual_spend_per_unit_eur", "low": 150, "base": 180, "high": 210,
     "source": "https://example.com/pricing-survey"},
]


@tool
def web_search(query: str) -> list[dict]:
    """Search the web for market figures."""
    if settings.search_backend == "mock":
        return MOCK_RESULTS
    response = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": settings.tavily_api_key, "query": query, "max_results": 3},
        timeout=30,
    )
    response.raise_for_status()
    # Real pages have no clean numbers; an extraction step would read them.
    return [{"source": r["url"], "snippet": r["content"]} for r in response.json()["results"]]


@tool
async def statista_lookup(topic: str) -> dict:
    """Look up structured market data (Statista-style) through MCP."""
    if not settings.mcp_enabled:
        return {"metric": "installed_base_units", "low": 10_500_000, "base": 11_500_000,
                "high": 13_000_000, "source": "statista (offline copy)"}

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Start the MCP server as a subprocess and talk to it over stdin/stdout.
    server = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("statista_lookup", {"topic": topic})
    if result.isError:
        raise RuntimeError(f"MCP tool failed: {result.content}")
    return json.loads(result.content[0].text)


TOOLS = [web_search, statista_lookup]
