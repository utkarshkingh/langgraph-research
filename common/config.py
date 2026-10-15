"""Central settings. One place to see every knob; everything has a demo-safe default."""
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
    research_mode: str = "inproc"          # inproc | http
    research_agent_url: str = "http://localhost:8081"

    # checkpointer
    checkpoint_backend: str = "sqlite"     # sqlite | postgres
    sqlite_path: str = "./checkpoints.sqlite"
    postgres_dsn: str = ""

    # model
    model_backend: str = "scripted"        # scripted | azure_openai
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # tools
    search_backend: str = "mock"           # mock | tavily
    tavily_api_key: str = ""
    mcp_enabled: bool = False


settings = Settings()
