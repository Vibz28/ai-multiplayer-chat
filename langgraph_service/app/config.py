from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_title: str = "AI Multiplayer Chat LangGraph Service"
    postgres_dsn: str = "postgresql://postgres:postgres@postgres:5432/langgraph"
    redis_url: str = "redis://redis:6379/0"
    ollama_primary_base_url: str = "http://host.docker.internal:11434"
    ollama_primary_model: str = "kimi-k2.5:cloud"
    ollama_fallback_cloud_base_url: str = "http://host.docker.internal:11434"
    ollama_fallback_cloud_model: str = "qwen3-vl:235b-cloud"
    ollama_fallback_local_base_url: str = "http://host.docker.internal:11434"
    ollama_fallback_local_model: str = "gpt-oss:20b"
    agent_prompt_manifest_path: str = "agent_prompts/system_prompt.yaml"
    agent_prompt_hub_identifier: str | None = None
    agent_system_prompt_fallback: str = (
        "You are the orchestration agent for a multi-service chat platform. "
        "Use tools when they improve correctness, especially for math, time, and session context. "
        "Return concise Markdown."
    )
    langsmith_tracing: bool = True
    langsmith_project: str = "ai-multiplayer-chat"

    model_config = SettingsConfigDict(
        env_prefix="LANGGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
