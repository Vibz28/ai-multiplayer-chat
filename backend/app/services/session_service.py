from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from app.id_factory import generate_application_id
from app.repositories.mapping_repository import (
    MappingConflictError,
    MappingNotFoundError,
    MappingRecord,
    MappingRepository,
)
from app.services.langgraph_client import LangGraphClientProtocol


class SessionService:
    def __init__(
        self,
        *,
        repository: MappingRepository,
        langgraph_client: LangGraphClientProtocol,
        application_id_prefix: str,
    ) -> None:
        self._repository = repository
        self._langgraph_client = langgraph_client
        self._application_id_prefix = application_id_prefix

    async def create_session(self, profile_id: str | None, role: str | None) -> MappingRecord:
        application_id = generate_application_id(self._application_id_prefix)
        return await run_in_threadpool(
            self._repository.create_application,
            application_id,
            profile_id,
            role,
        )

    async def get_session(self, application_id: str) -> MappingRecord | None:
        return await run_in_threadpool(self._repository.get_mapping, application_id)

    async def ensure_thread(self, application_id: str) -> MappingRecord:
        mapping = await self.get_session(application_id)
        if mapping is None:
            raise MappingNotFoundError(application_id)

        if mapping.langgraph_thread_id:
            return mapping

        thread_id = await self._langgraph_client.create_thread(application_id)
        try:
            return await run_in_threadpool(
                self._repository.assign_thread,
                application_id,
                thread_id,
            )
        except MappingConflictError:
            resolved = await self.get_session(application_id)
            if resolved is None or resolved.langgraph_thread_id is None:
                raise
            return resolved
