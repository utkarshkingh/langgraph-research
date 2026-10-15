"""A tiny MCP server with one tool, standing in for a Statista data connector.

The research agent starts it as a subprocess (stdio transport) when MCP_ENABLED=true.
Run it alone with:  python mcp_server/statista_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("statista")


@mcp.tool()
def statista_lookup(topic: str) -> dict:
    """Return a low/base/high estimate for a market topic."""
    return {
        "metric": "installed_base_units",
        "low": 10_500_000,
        "base": 11_500_000,
        "high": 13_000_000,
        "source": f"statista: {topic}",
    }


if __name__ == "__main__":
    mcp.run()  # stdio
