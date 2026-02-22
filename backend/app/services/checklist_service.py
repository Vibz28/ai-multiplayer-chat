from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from app.models import ChecklistItemResponse, SessionChecklistResponse
from app.repositories.mapping_repository import MappingNotFoundError, MappingRepository
from app.services.langgraph_client import LangGraphClientProtocol


class CanonicalChecklistService:
    """Backend abstraction over thread-scoped checklist state in LangGraph runtime."""

    def __init__(
        self,
        *,
        mapping_repository: MappingRepository,
        langgraph_client: LangGraphClientProtocol,
    ) -> None:
        self._mapping_repository = mapping_repository
        self._langgraph_client = langgraph_client

    async def get_application_checklist(self, *, application_id: str) -> SessionChecklistResponse:
        mapping = await run_in_threadpool(self._mapping_repository.get_mapping, application_id)
        if mapping is None:
            raise MappingNotFoundError(application_id)
        if mapping.langgraph_thread_id is None:
            raise MappingNotFoundError(application_id)

        items = await self._langgraph_client.get_thread_checklist(thread_id=mapping.langgraph_thread_id)
        response_items = [
            ChecklistItemResponse(index=item.index, text=item.text, done=item.done)
            for item in items
        ]
        return SessionChecklistResponse(
            application_id=application_id,
            langgraph_thread_id=mapping.langgraph_thread_id,
            workflow_id=mapping.workflow_id,
            langsmith_trace_id=mapping.langsmith_trace_id,
            items=response_items,
            count=len(response_items),
        )
