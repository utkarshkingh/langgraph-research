"""Orchestrator service: its agent card + the shared A2A app.

Run:  uvicorn orchestrator.main:app --port 8000
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
from orchestrator.graph import build_graph

agent_card = AgentCard(
    name="Market Sizing Orchestrator",
    description="Runs a market-sizing request: calls the Research Agent over A2A "
                "and relays its review questions to the user.",
    version="1.0.0",
    supported_interfaces=[AgentInterface(protocol_binding="JSONRPC",
                                         url=settings.orchestrator_url,
                                         protocol_version="1.0")],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain", "application/json"],
    default_output_modes=["application/json"],
    skills=[AgentSkill(
        id="size_market",
        name="Size a market",
        description="Returns a report built from human-approved research assumptions.",
        tags=["orchestrator", "market-sizing"],
        examples=["Size the European EV charging aftermarket"],
    )],
    security_schemes={"bearer": SecurityScheme(
        http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="bearer"))},
    security_requirements=[SecurityRequirement(schemes={"bearer": StringList()})],
)

app = create_app(agent_card, build_graph)
