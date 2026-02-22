from __future__ import annotations

import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

service_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(service_root))

previous_app = sys.modules.get('app')
scoped_app_module = types.ModuleType('app')
scoped_app_module.__path__ = [str(service_root / 'app')]  # type: ignore[attr-defined]
sys.modules['app'] = scoped_app_module

config_spec = spec_from_file_location('langgraph_service_config', service_root / 'app' / 'config.py')
if config_spec is None or config_spec.loader is None:
    raise RuntimeError('Unable to load langgraph_service config module')
config_module = module_from_spec(config_spec)
config_spec.loader.exec_module(config_module)

loader_spec = spec_from_file_location('langgraph_service_prompt_loader', service_root / 'app' / 'prompt_loader.py')
if loader_spec is None or loader_spec.loader is None:
    raise RuntimeError('Unable to load langgraph_service prompt_loader module')
loader_module = module_from_spec(loader_spec)
loader_spec.loader.exec_module(loader_module)

if previous_app is not None:
    sys.modules['app'] = previous_app
else:
    sys.modules.pop('app', None)

Settings = config_module.Settings
load_agent_prompt_template = loader_module.load_agent_prompt_template


def test_load_agent_prompt_template_from_local_manifest() -> None:
    settings = Settings(
        agent_prompt_manifest_path='agent_prompts/system_prompt.yaml',
        agent_prompt_hub_identifier=None,
    )

    prompt = load_agent_prompt_template(settings)
    messages = prompt.format_messages(
        application_id='app_1',
        thread_id='thread_1',
        profile_id='profile_1',
        user_message='hello',
    )

    assert len(messages) == 2
    assert messages[0].type == 'system'
    assert 'application_id: app_1' in str(messages[0].content)
    assert messages[1].type == 'human'
    assert str(messages[1].content) == 'hello'


def test_load_agent_prompt_template_falls_back_when_hub_and_manifest_fail(monkeypatch) -> None:
    settings = Settings(
        agent_prompt_manifest_path='agent_prompts/does-not-exist.yaml',
        agent_prompt_hub_identifier='Vibz28/ai-multiplayer-chat:latest',
        agent_system_prompt_fallback='fallback system prompt text',
    )

    def _raise_hub_error(prompt_identifier: str):
        raise RuntimeError(f'Unable to load {prompt_identifier}')

    monkeypatch.setattr(loader_module, 'load_prompt_from_hub', _raise_hub_error)

    prompt = load_agent_prompt_template(settings)
    messages = prompt.format_messages(user_message='run fallback path')

    assert len(messages) == 2
    assert messages[0].type == 'system'
    assert str(messages[0].content) == 'fallback system prompt text'
    assert messages[1].type == 'human'
    assert str(messages[1].content) == 'run fallback path'
