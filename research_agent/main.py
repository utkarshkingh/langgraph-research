"""Research agent as an A2A server (official a2a-sdk, mounted on FastAPI).

  GET  /.well-known/agent-card.json   the agent card (public): who I am, my skill, how to auth
  POST /                              the A2A JSON-RPC endpoint (SendMessage, GetTask, ...)
  GET  /health                        unauthenticated liveness

Everything except the card and /health needs `Authorization: Bearer <token>`
(common/security.py). The research logic is in research_agent/graph.py; executor.py
maps it to A2A task states. The task store keeps each task between gather and finalize;
durable run state for the whole job still lives in the orchestrator.

Run:  uvicorn research_agent.main:app --port 8081
"""
from __future__ import annotations

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import DatabaseTaskStore, InMemoryTaskStore, TaskStore
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
from fastapi import FastAPI

from common.config import settings
from common.security import require_bearer_token
from research_agent.executor import ResearchExecutor


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="Research Agent",
        description="Finds low/base/high market figures with web search and Statista (MCP), "
                    "then asks a human to approve them.",
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(
            id="research_market",
            name="Research market figures",
            description="Proposes low/base/high assumptions, each with a source status, "
                        "then validates the ones a human approves.",
            tags=["research", "market-sizing"],
            examples=["Size the European EV charging aftermarket"],
        )],
        # Tells callers how to authenticate: a bearer token.
        security_schemes={"bearer": SecurityScheme(
            http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="bearer"))},
        security_requirements=[SecurityRequirement(schemes={"bearer": StringList()})],
    )


def create_task_store() -> TaskStore:
    """Postgres by default (any replica can continue a task); memory for tests only."""
    if settings.task_store_backend == "memory":
        return InMemoryTaskStore()

    if not settings.postgres_dsn:
        raise ValueError(
            "POSTGRES_DSN is empty. Set it in .env (see .env.example), "
            "or TASK_STORE_BACKEND=memory for tests."
        )
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = settings.postgres_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return DatabaseTaskStore(create_async_engine(dsn), create_table=True)


def create_app(url: str | None = None) -> FastAPI:
    card = build_agent_card(url or settings.research_agent_url)
    handler = DefaultRequestHandler(
        agent_executor=ResearchExecutor(),
        task_store=create_task_store(),
        agent_card=card,
    )

    app = FastAPI(title=card.name)
    app.middleware("http")(require_bearer_token)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
