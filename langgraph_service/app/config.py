from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_title: str = "AI Multiplayer Chat LangGraph Service"
    postgres_dsn: str = "postgresql://postgres:postgres@postgres:5432/langgraph"
    redis_url: str = "redis://redis:6379/0"
    ollama_primary_base_url: str = "http://host.docker.internal:11434"
    ollama_primary_model: str = "kimi-k2.7-code:cloud"
    ollama_fallback_cloud_base_url: str = "http://host.docker.internal:11434"
    ollama_fallback_cloud_model: str = "gpt-oss:120b-cloud"
    worker_runtime_url: str = "http://worker-runtime:8090"
    codex_runtime_url: str = "http://codex-runtime:8090"
    claude_runtime_url: str = "http://claude-runtime:8090"
    opencode_runtime_url: str = "http://opencode-runtime:8090"
    pi_runtime_url: str = "http://pi-runtime:8090"
    runtime_token: str = "local-runtime-secret-change-me"
    service_token: str = "local-langgraph-secret-change-me"
    agent_prompt_manifest_path: str = "agent_prompts/system_prompt.yaml"
    agent_prompt_hub_identifier: str | None = None
    agent_system_prompt_fallback: str = (
        "You are Moss, a dependable digital worker. "
        "Report outcomes, deliverables, and review needs in plain language."
    )
    langsmith_tracing: bool = True
    langsmith_project: str = "ai-multiplayer-chat"

    @field_validator("ollama_primary_model", "ollama_fallback_cloud_model")
    @classmethod
    def require_cloud_model(cls, value: str) -> str:
        allowed = {"kimi-k2.7-code:cloud", "gpt-oss:120b-cloud"}
        if value not in allowed:
            raise ValueError("Fieldwork only permits its reviewed Ollama Cloud model allowlist")
        return value

    model_config = SettingsConfigDict(
        env_prefix="LANGGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
