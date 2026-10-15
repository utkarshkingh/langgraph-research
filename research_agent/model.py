"""The 'brain' behind the ReAct loop, behind a tiny interface so it is swappable.

decide() looks at the query and the evidence gathered so far and returns the next
action: call a tool, or finish with a set of proposed assumptions.

  MODEL_BACKEND=litellm      -> DEFAULT. Company LiteLLM gateway, structured output.
  MODEL_BACKEND=azure_openai -> Azure OpenAI with managed identity (no API key).
  MODEL_BACKEND=scripted     -> deterministic test double, no LLM. Used by the tests and
                                the offline backup demo only.

Keeping one interface means the graph (graph.py) is identical whichever brain is used.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from common.config import settings


class Decision(BaseModel):
    action: Literal["tool", "finish"]
    tool: str | None = None
    args: dict[str, Any] = {}
    proposed: list[dict[str, Any]] = []   # populated when action == "finish"


class Model:
    def decide(self, query: str, evidence: list[dict[str, Any]]) -> Decision:  # noqa: D401
        raise NotImplementedError


class ScriptedModel(Model):
    """Deterministic ReAct policy for the offline demo.

    Step 0: no evidence yet          -> call web_search
    Step 1: have web evidence        -> call statista_lookup (over MCP)
    Step 2: have both                -> finish, proposing assumptions from the evidence
    """

    def decide(self, query: str, evidence: list[dict[str, Any]]) -> Decision:
        tools_used = {e["tool"] for e in evidence}

        if "web_search" not in tools_used:
            return Decision(action="tool", tool="web_search", args={"query": query})

        if "statista_lookup" not in tools_used:
            return Decision(action="tool", tool="statista_lookup", args={"topic": query})

        return Decision(action="finish", proposed=self._propose(evidence))

    @staticmethod
    def _propose(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Turn raw observations into assumptions with a source status.

        source_status taxonomy (the defensibility story):
          research_value   - taken from a primary observation
          support_range    - derived corroborating band
          heuristic_fallback - no source; the agent guessed and SAYS so
        """
        proposed: list[dict[str, Any]] = []

        def _emit(name: str, band: dict[str, Any], tool: str) -> None:
            if {"low", "base", "high"} <= band.keys():
                proposed.append(
                    {
                        "name": name,
                        "low": band["low"],
                        "base": band["base"],
                        "high": band["high"],
                        "source_status": "research_value",
                        "evidence_tool": tool,
                    }
                )

        for i, e in enumerate(evidence):
            result = e.get("result")
            tool = e["tool"]
            if isinstance(result, dict):
                # structured tool (e.g. Statista via MCP)
                band = result.get("value_hint", result)
                _emit(f"{tool}_estimate", band, tool)
            elif isinstance(result, list):
                # web search: each hit may carry a value_hint band
                for j, hit in enumerate(result):
                    band = hit.get("value_hint", {}) if isinstance(hit, dict) else {}
                    _emit(f"{tool}_{j}", band, tool)
        if not proposed:
            # No usable number anywhere -> declare a heuristic fallback rather than hide it.
            proposed.append(
                {
                    "name": "fallback_estimate",
                    "low": 1,
                    "base": 2,
                    "high": 3,
                    "source_status": "heuristic_fallback",
                    "evidence_tool": None,
                }
            )
        return proposed


class LLMModel(Model):  # pragma: no cover - needs a real LLM endpoint
    """The real brain: a chat model that must answer with a valid Decision."""

    def __init__(self, llm: Any) -> None:
        # Structured output: the model must return a valid Decision, not free text.
        self._llm = llm.with_structured_output(Decision, method="function_calling")

    def decide(self, query: str, evidence: list[dict[str, Any]]) -> Decision:
        import json

        system = (
            "You are a market-research planner. Given the query and the evidence so far, "
            "either call a tool (web_search with args.query, or statista_lookup with "
            "args.topic) or finish with proposed assumptions {name, low, base, high, "
            "source_status}. Use source_status in "
            "{research_value, support_range, heuristic_fallback}."
        )
        user = json.dumps({"query": query, "evidence": evidence})
        return self._llm.invoke([("system", system), ("user", user)])


def _litellm_chat_model() -> Any:
    """Company LiteLLM gateway (OpenAI-compatible), same settings as the other agents.

    The endpoint and virtual key are supplied by the deployment; blank here on purpose.
    """
    from langchain_openai import ChatOpenAI

    values = {
        "LITELLM_BASE_URL": settings.litellm_base_url,
        "LITELLM_DEFAULT_MODEL": settings.litellm_default_model,
        "LITELLM_VIRTUAL_KEY": settings.litellm_virtual_key,
    }
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise ValueError(
            "LiteLLM model configuration is incomplete: " + ", ".join(missing)
            + ". Set them in .env (see .env.example), or MODEL_BACKEND=scripted for the offline demo."
        )
    return ChatOpenAI(
        model=settings.litellm_default_model,
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_virtual_key,
        temperature=0,
        timeout=600,
    )


def _azure_openai_chat_model() -> Any:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from langchain_openai import AzureChatOpenAI

    # Managed identity, no API key: Entra issues tokens for Azure OpenAI.
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
        temperature=0,
    )


def build_model() -> Model:
    if settings.model_backend == "scripted":      # offline test double: tests and backup demo only
        return ScriptedModel()
    if settings.model_backend == "azure_openai":
        return LLMModel(_azure_openai_chat_model())
    return LLMModel(_litellm_chat_model())        # default: litellm
