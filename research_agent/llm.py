"""The chat model that drives the ReAct loop.

    LLM_BACKEND=azure_openai  Azure OpenAI, signed in with managed identity (no API key)
    LLM_BACKEND=scripted      offline stand-in with the same interface: invoke(messages)
                              returns an AIMessage, with tool_calls when it wants a tool

The graph cannot tell the two apart, so the offline demo runs the real loop.
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from common.config import settings
from research_agent.tools import TOOLS


def build_llm():
    if settings.llm_backend == "azure_openai":
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from langchain_openai import AzureChatOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            azure_ad_token_provider=token_provider,
            temperature=0,
        )
        return llm.bind_tools(TOOLS)  # the model may now answer with tool calls
    return ScriptedLLM()


class ScriptedLLM:
    """Calls web_search, then statista_lookup, then stops."""

    def invoke(self, messages):
        topic = next(m.content for m in messages if isinstance(m, HumanMessage))
        used = {m.name for m in messages if isinstance(m, ToolMessage)}
        if "web_search" not in used:
            return _tool_call("web_search", {"query": topic})
        if "statista_lookup" not in used:
            return _tool_call("statista_lookup", {"topic": topic})
        return AIMessage(content="I have enough evidence.")


def _tool_call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}])
