"""Central settings. One place to see every knob.

The defaults are the real setup: LiteLLM model, Postgres checkpoints, two services
over HTTP, real search and MCP. Secrets are blank; fill them in .env (see .env.example).
Tests and the offline backup demo switch parts off with environment variables.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # auth
    auth_mode: str = "dev"                 # dev | entra
    dev_token: str = "local-dev-token"
    entra_tenant_id: str = ""
    entra_api_audience: str = ""
    research_agent_app_id_uri: str = ""

    # service wiring
    research_mode: str = "http"            # http | inproc (tests)
    research_agent_url: str = "http://localhost:8081"

    # checkpointer
    checkpoint_backend: str = "postgres"   # postgres | sqlite (tests)
    postgres_dsn: str = ""                 # postgresql://agent:<password>@localhost:5432/agent
    sqlite_path: str = "./checkpoints.sqlite"

    # model
    model_backend: str = "litellm"         # litellm | azure_openai | scripted (tests)
    litellm_base_url: str = ""             # https://<approved-company-litellm>/v1
    litellm_default_model: str = ""
    litellm_virtual_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # tools
    search_backend: str = "tavily"         # tavily | mock (tests)
    tavily_api_key: str = ""
    mcp_enabled: bool = True               # real MCP server over stdio


settings = Settings()
