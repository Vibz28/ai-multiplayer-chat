from functools import lru_cache

from app.config import get_settings
from app.repositories.mapping_repository import DynamoDBMappingRepository
from app.services.langgraph_client import LangGraphClient
from app.services.session_service import SessionService
from app.services.websocket_hub import WebSocketHub


@lru_cache
def get_mapping_repository() -> DynamoDBMappingRepository:
    settings = get_settings()
    return DynamoDBMappingRepository(
        table_name=settings.dynamodb_table_name,
        endpoint_url=settings.dynamodb_endpoint_url,
        region_name=settings.dynamodb_region,
        access_key_id=settings.dynamodb_access_key_id,
        secret_access_key=settings.dynamodb_secret_access_key,
    )


@lru_cache
def get_langgraph_client() -> LangGraphClient:
    settings = get_settings()
    return LangGraphClient(base_url=settings.langgraph_service_url)


@lru_cache
def get_session_service() -> SessionService:
    settings = get_settings()
    return SessionService(
        repository=get_mapping_repository(),
        langgraph_client=get_langgraph_client(),
        application_id_prefix=settings.application_id_prefix,
    )


@lru_cache
def get_websocket_hub() -> WebSocketHub:
    return WebSocketHub()
