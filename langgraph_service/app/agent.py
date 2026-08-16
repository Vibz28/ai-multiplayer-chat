from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent_tooling import (
    fetch_web,
    get_checklist_items,
    list_workspace,
    manage_checklist,
    read_workspace_file,
    register_artifact,
    workspace_edit,
    workspace_exec,
    workspace_read,
    workspace_search,
    write_workspace_file,
)
from app.config import get_settings
from app.prompt_loader import load_agent_prompt_template


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


class AgentWorkflowState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    application_id: str
    thread_id: str
    profile_id: str | None
    user_message: str


def _extract_user_message(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return coerce_message_content(message.content)
        if isinstance(message, dict):
            role = str(message.get("role", ""))
            if role in {"user", "human"}:
                return coerce_message_content(message.get("content", ""))
    return ""


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
    llm = primary_llm.with_fallbacks([fallback_cloud_llm])

    prompt_template = load_agent_prompt_template(settings)

    react_agent = create_agent(
        model=llm,
        tools=[
            get_utc_time,
            add_numbers,
            describe_session_context,
            manage_checklist,
            workspace_search,
            workspace_read,
            workspace_edit,
            workspace_exec,
            fetch_web,
            register_artifact,
        ],
        system_prompt=None,
        name="react_autonomous_node",
    )

    def prepare_context_messages(state: AgentWorkflowState) -> dict[str, Any]:
        user_message = state.get("user_message") or _extract_user_message(state.get("messages", []))
        prompt_messages = prompt_template.format_messages(
            application_id=state.get("application_id", "unknown"),
            thread_id=state.get("thread_id", "unknown"),
            profile_id=state.get("profile_id") or "unknown",
            user_message=user_message,
        )
        return {"messages": prompt_messages, "user_message": user_message}

    async def run_react_agent(state: AgentWorkflowState) -> dict[str, Any]:
        result = await react_agent.ainvoke(
            {"messages": state["messages"]},
            config={
                "configurable": {
                    "thread_id": state.get("thread_id"),
                    "application_id": state.get("application_id"),
                    "profile_id": state.get("profile_id"),
                }
            },
        )
        return {"messages": result.get("messages", [])}

    def finalize_turn(_: AgentWorkflowState) -> dict[str, Any]:
        return {}

    workflow = StateGraph(AgentWorkflowState)
    workflow.add_node("prepare_context", prepare_context_messages)
    workflow.add_node("react_autonomous", run_react_agent)
    workflow.add_node("finalize_turn", finalize_turn)
    workflow.add_edge(START, "prepare_context")
    workflow.add_edge("prepare_context", "react_autonomous")
    workflow.add_edge("react_autonomous", "finalize_turn")
    workflow.add_edge("finalize_turn", END)
    return workflow.compile()


def coerce_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part) for part in content)
    return str(content)


__all__ = [
    "add_numbers",
    "coerce_message_content",
    "describe_session_context",
    "get_checklist_items",
    "get_compiled_graph",
    "get_utc_time",
    "list_workspace",
    "manage_checklist",
    "read_workspace_file",
    "write_workspace_file",
]
