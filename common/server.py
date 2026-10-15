"""Builds the FastAPI app for an A2A agent. Both services use it.

Every agent app has the same four things:
    GET  /.well-known/agent-card.json   the agent card (public): who I am, my skills, how to auth
    POST /                              the A2A JSON-RPC endpoint (SendMessage, GetTask, ...)
    GET  /health                        liveness probe for Container Apps
    bearer-token middleware             see common/security.py

Only the agent card and the graph differ per service.
"""
from contextlib import asynccontextmanager

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.types import AgentCard
from fastapi import FastAPI

from common.agent_executor import LangGraphAgentExecutor
from common.persistence import create_task_store, open_checkpointer
from common.security import require_bearer_token


def create_app(agent_card: AgentCard, build_graph) -> FastAPI:
    executor = LangGraphAgentExecutor()
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=create_task_store(),
        agent_card=agent_card,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The checkpointer stays open while the app runs; the graph is compiled with it.
        async with open_checkpointer() as checkpointer:
            executor.graph = build_graph(checkpointer)
            yield

    app = FastAPI(title=agent_card.name, lifespan=lifespan)
    app.middleware("http")(require_bearer_token)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
