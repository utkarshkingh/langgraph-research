"""A tiny local MCP server exposing a Statista-style market-data tool over stdio.

Run standalone:   python mcp_server/statista_stub.py   (speaks MCP on stdio)
Or let research_agent/tools/mcp_client.py spawn it when MCP_ENABLED=true.

Requires the `mcp` extra:  pip install -e '.[mcp]'
"""
from __future__ import annotations

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise SystemExit("install the 'mcp' extra to run this server: pip install -e '.[mcp]'") from e

mcp = FastMCP("statista-stub")


@mcp.tool()
def statista_lookup(topic: str) -> dict:
    """Return a base estimate, a low/high support range, and historical CAGR for a topic."""
    return {
        "topic": topic,
        "base": 11_500_000,
        "low": 10_500_000,
        "high": 13_000_000,
        "historical_cagr": 0.06,
        "source": "statista-stub",
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
