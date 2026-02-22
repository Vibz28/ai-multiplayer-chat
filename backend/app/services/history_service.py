from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from app.models import HistoryEntryResponse, SessionHistoryResponse
from app.repositories.mapping_repository import MappingNotFoundError, MappingRepository
from app.services.langgraph_client import LangGraphClientProtocol


class CanonicalHistoryService:
    """Backend abstraction over canonical thread history in LangGraph Postgres/Redis."""

    def __init__(
        self,
        *,
        mapping_repository: MappingRepository,
        langgraph_client: LangGraphClientProtocol,
    ) -> None:
        self._mapping_repository = mapping_repository
        self._langgraph_client = langgraph_client

    async def get_application_history(
        self,
        *,
        application_id: str,
        limit: int,
    ) -> SessionHistoryResponse:
        mapping = await run_in_threadpool(self._mapping_repository.get_mapping, application_id)
        if mapping is None:
            raise MappingNotFoundError(application_id)
        if mapping.langgraph_thread_id is None:
            raise MappingNotFoundError(application_id)

        entries = await self._langgraph_client.get_thread_history(
            thread_id=mapping.langgraph_thread_id,
            limit=limit,
        )
        response_entries = [
            HistoryEntryResponse(
                application_id=entry.application_id,
                thread_id=entry.thread_id,
                profile_id=entry.profile_id,
                role=entry.role,
                channel=entry.channel,
                content=entry.content,
                run_id=entry.run_id,
                trace_id=entry.trace_id,
                metadata=entry.metadata,
                created_at=entry.created_at,
            )
            for entry in entries
        ]
        return SessionHistoryResponse(
            application_id=application_id,
            langgraph_thread_id=mapping.langgraph_thread_id,
            profile_id=mapping.profile_id,
            role=mapping.role,
            workflow_id=mapping.workflow_id,
            langsmith_trace_id=mapping.langsmith_trace_id,
            entries=response_entries,
            count=len(response_entries),
        )
