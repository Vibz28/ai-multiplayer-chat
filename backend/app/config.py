from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    api_title: str = "AI Multiplayer Chat Backend"

    dynamodb_table_name: str = "application_thread_mapping"
    dynamodb_endpoint_url: str = "http://dynamodb-local:8000"
    dynamodb_region: str = "us-east-1"
    dynamodb_access_key_id: str = "dummy"
    dynamodb_secret_access_key: str = "dummy"

    langgraph_service_url: str = "http://langgraph-service:8080"
    langgraph_service_token: str = "local-langgraph-secret-change-me"
    worker_runtime_url: str = "http://worker-runtime:8090"
    runtime_token: str = "local-runtime-secret-change-me"
    application_id_prefix: str = "app"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    room_token_secret: str = "local-development-secret-change-me"

    model_config = SettingsConfigDict(
        env_prefix="BACKEND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
