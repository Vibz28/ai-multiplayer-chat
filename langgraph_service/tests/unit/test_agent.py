from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

service_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(service_root))

agent_spec = spec_from_file_location("langgraph_service_agent", service_root / "app" / "agent.py")
if agent_spec is None or agent_spec.loader is None:
    raise RuntimeError("Unable to load langgraph_service agent module")
agent_module = module_from_spec(agent_spec)
agent_spec.loader.exec_module(agent_module)

add_numbers = agent_module.add_numbers
coerce_message_content = agent_module.coerce_message_content
describe_session_context = agent_module.describe_session_context
get_utc_time = agent_module.get_utc_time


def test_add_numbers_tool() -> None:
    assert add_numbers.invoke({"a": 2.5, "b": 7.5}) == 10.0


def test_describe_session_context_tool() -> None:
    result = describe_session_context.invoke(
        {
            "application_id": "app_1",
            "thread_id": "thread_1",
            "profile_id": "alpha",
        }
    )
    assert "application_id=app_1" in result
    assert "thread_id=thread_1" in result
    assert "profile_id=alpha" in result


def test_get_utc_time_tool_returns_iso_timestamp() -> None:
    value = get_utc_time.invoke({})
    assert "T" in value
    assert value.endswith("+00:00")


def test_coerce_message_content_normalizes_supported_types() -> None:
    assert coerce_message_content("hello") == "hello"
    assert coerce_message_content(["a", "b"]) == "a\nb"
    assert coerce_message_content(123) == "123"
