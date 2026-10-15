"""Settings, read from environment variables (or a .env file).

Same code runs locally and in Azure; only these values change.
Every setting has a safe local default, so the demo needs no .env at all.
"""
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Authentication (see common/security.py) ---
    a2a_auth_mode: Literal["shared_secret", "entra", "easy_auth"] = "shared_secret"
    a2a_shared_secret: str = "local-dev-secret"   # local only
    a2a_entra_tenant_id: str = ""                 # entra mode
    a2a_entra_audience: str = ""                  # e.g. api://<app-id>, entra / easy_auth modes

    # --- Where the services live ---
    orchestrator_url: str = "http://localhost:8000"
    research_agent_url: str = "http://localhost:8001"

    # --- Persistence: empty = in memory (local), set = Postgres (production) ---
    postgres_dsn: str = ""

    # --- LLM and tools ---
    llm_backend: Literal["scripted", "azure_openai"] = "scripted"
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"
    search_backend: Literal["mock", "tavily"] = "mock"
    tavily_api_key: str = ""
    mcp_enabled: bool = False   # true = really call the MCP server over stdio


settings = Settings()
