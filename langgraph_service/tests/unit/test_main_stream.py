from __future__ import annotations

import json
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

service_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(service_root))

agent_spec = spec_from_file_location("langgraph_service_agent", service_root / "app" / "agent.py")
if agent_spec is None or agent_spec.loader is None:
    raise RuntimeError("Unable to load langgraph_service agent module")
agent_module = module_from_spec(agent_spec)
agent_spec.loader.exec_module(agent_module)

config_spec = spec_from_file_location("langgraph_service_config", service_root / "app" / "config.py")
if config_spec is None or config_spec.loader is None:
    raise RuntimeError("Unable to load langgraph_service config module")
config_module = module_from_spec(config_spec)
config_spec.loader.exec_module(config_module)

previous_app = sys.modules.get("app")
previous_app_agent = sys.modules.get("app.agent")
previous_app_config = sys.modules.get("app.config")
app_module = types.ModuleType("app")
app_module.__path__ = [str(service_root / "app")]  # type: ignore[attr-defined]
sys.modules["app"] = app_module

sys.modules["app.agent"] = agent_module
sys.modules["app.config"] = config_module
app_module.agent = agent_module
app_module.config = config_module

main_spec = spec_from_file_location("langgraph_service_main", service_root / "app" / "main.py")
if main_spec is None or main_spec.loader is None:
    raise RuntimeError("Unable to load langgraph_service main module")
main_module = module_from_spec(main_spec)
main_spec.loader.exec_module(main_module)

if previous_app is not None:
    sys.modules["app"] = previous_app
else:
    sys.modules.pop("app", None)
if previous_app_agent is not None:
    sys.modules["app.agent"] = previous_app_agent
else:
    sys.modules.pop("app.agent", None)
if previous_app_config is not None:
    sys.modules["app.config"] = previous_app_config
else:
    sys.modules.pop("app.config", None)

AgentRunRequest = main_module.AgentRunRequest
state = main_module.state


class SuccessfulGraph:
    async def ainvoke(self, _payload: dict, config: dict) -> dict:
        del config
        return {
            "messages": [
                ToolMessage(content="tool output", tool_call_id="tool-1"),
                AIMessage(
                    content="final answer",
                    response_metadata={
                        "model": "kimi-k2.5:cloud",
                        "prompt_eval_count": 8,
                        "eval_count": 6,
                    },
                    tool_calls=[
                        {
                            "id": "tool-call-1",
                            "name": "describe_session_context",
                            "type": "tool_call",
                            "args": {"application_id": "app-stream"},
                        }
                    ],
                ),
            ]
        }

    async def astream_events(self, _payload: dict, config: dict, version: str):
        del config, version
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="final ")}}
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="answer")}}
        yield {
            "event": "on_tool_end",
            "data": {"output": ToolMessage(content="tool output", tool_call_id="tool-1")},
        }
        yield {
            "event": "on_chat_model_end",
            "data": {
                "output": AIMessage(
                    content="final answer",
                    response_metadata={
                        "model": "kimi-k2.5:cloud",
                        "prompt_eval_count": 8,
                        "eval_count": 6,
                    },
                    tool_calls=[
                        {
                            "id": "tool-call-1",
                            "name": "describe_session_context",
                            "type": "tool_call",
                            "args": {"application_id": "app-stream"},
                        }
                    ],
                )
            },
        }


class FailingGraph:
    async def ainvoke(self, _payload: dict, config: dict) -> dict:
        del config
        raise RuntimeError("upstream unavailable")

    async def astream_events(self, _payload: dict, config: dict, version: str):
        del config, version
        raise RuntimeError("upstream unavailable")
        yield {}  # pragma: no cover


async def collect_events(request: AgentRunRequest) -> list[dict]:
    events: list[dict] = []
    async for chunk in main_module._agent_event_stream(request):
        events.append(json.loads(chunk.decode()))
    return events


@pytest.mark.asyncio
async def test_agent_stream_emits_reasoning_content_and_complete() -> None:
    original_graph = state.agent_graph
    state.agent_graph = SuccessfulGraph()

    try:
        events = await collect_events(
            AgentRunRequest(
                application_id="app-stream",
                thread_id="thread-stream",
                profile_id="profile-stream",
                message="hello",
            )
        )
    finally:
        state.agent_graph = original_graph

    assert events[0]["type"] == "status"
    assert events[0]["stream_state"] == "queued"
    assert [event["type"] for event in events][-1] == "complete"
    assert "run_id" in events[0]["payload"]["run"]
    assert events[0]["payload"]["run"]["status"] == "running"

    reasoning_deltas = [event["payload"]["delta"] for event in events if event["type"] == "reasoning"]
    content_deltas = [event["payload"]["delta"] for event in events if event["type"] == "content"]
    completion_run = events[-1]["payload"]["run"]

    assert "".join(reasoning_deltas) == "tool output"
    assert "".join(content_deltas) == "final answer"
    assert completion_run["status"] == "completed"
    assert completion_run["model_selected"] == "kimi-k2.5:cloud"
    assert completion_run["token_usage"]["prompt_tokens"] == 8
    assert completion_run["token_usage"]["completion_tokens"] == 6
    assert completion_run["tool_call_count"] == 1
    assert completion_run["content_chunk_count"] >= 1


@pytest.mark.asyncio
async def test_agent_stream_emits_error_event_on_failure() -> None:
    original_graph = state.agent_graph
    state.agent_graph = FailingGraph()

    try:
        events = await collect_events(
            AgentRunRequest(
                application_id="app-stream",
                thread_id="thread-stream",
                profile_id="profile-stream",
                message="hello",
            )
        )
    finally:
        state.agent_graph = original_graph

    assert [event["type"] for event in events] == ["status", "error"]
    assert events[1]["stream_state"] == "error"
    assert "Agent stream failed" in events[1]["payload"]["message"]
    assert events[1]["payload"]["run"]["status"] == "error"
    assert events[1]["payload"]["run"]["error"] is not None
