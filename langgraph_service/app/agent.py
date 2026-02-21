from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from app.config import get_settings


@tool
def get_utc_time() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@tool
def add_numbers(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b


@tool
def describe_session_context(
    application_id: str,
    thread_id: str,
    profile_id: str | None = None,
) -> str:
    """Summarize known session context values."""
    return (
        f"application_id={application_id}; thread_id={thread_id}; "
        f"profile_id={profile_id or 'unknown'}"
    )


def get_compiled_graph() -> Any:
    settings = get_settings()
    primary_llm = ChatOllama(
        model=settings.ollama_primary_model,
        base_url=settings.ollama_primary_base_url,
        temperature=0,
    )
    fallback_cloud_llm = ChatOllama(
        model=settings.ollama_fallback_cloud_model,
        base_url=settings.ollama_fallback_cloud_base_url,
        temperature=0,
    )
    fallback_local_llm = ChatOllama(
        model=settings.ollama_fallback_local_model,
        base_url=settings.ollama_fallback_local_base_url,
        temperature=0,
    )
    llm = primary_llm.with_fallbacks([fallback_cloud_llm, fallback_local_llm])
    return create_react_agent(
        model=llm,
        tools=[get_utc_time, add_numbers, describe_session_context],
        prompt=settings.agent_system_prompt,
    )


def coerce_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part) for part in content)
    return str(content)
