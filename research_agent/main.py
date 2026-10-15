"""Research agent service: its agent card + the shared A2A app.

Run:  uvicorn research_agent.main:app --port 8001
"""
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)

from common.config import settings
from common.server import create_app
from research_agent.graph import build_graph

agent_card = AgentCard(
    name="Research Agent",
    description="Finds low/base/high market figures with web search and Statista (MCP), "
                "then asks a human to approve them.",
    version="1.0.0",
    supported_interfaces=[AgentInterface(protocol_binding="JSONRPC",
                                         url=settings.research_agent_url,
                                         protocol_version="1.0")],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain", "application/json"],
    default_output_modes=["application/json"],
    skills=[AgentSkill(
        id="research_market",
        name="Research market figures",
        description="Returns reviewed assumptions, each with a source and source status.",
        tags=["research", "market-sizing"],
        examples=["Size the European EV charging aftermarket"],
    )],
    # Tells callers how to authenticate: a bearer token.
    security_schemes={"bearer": SecurityScheme(
        http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="bearer"))},
    security_requirements=[SecurityRequirement(schemes={"bearer": StringList()})],
)

app = create_app(agent_card, build_graph)
