from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock

from app.repositories.mapping_repository import (
    MappingConflictError,
    MappingNotFoundError,
    MappingRecord,
)


class InMemoryMappingRepository:
    def __init__(self) -> None:
        self._records: dict[str, MappingRecord] = {}
        self._lock = Lock()

    def ensure_table(self) -> None:
        return

    def ping(self) -> bool:
        return True

    def create_application(self, application_id: str, profile_id: str | None) -> MappingRecord:
        with self._lock:
            if application_id in self._records:
                raise MappingConflictError(application_id)
            now = datetime.now(UTC)
            record = MappingRecord(
                application_id=application_id,
                profile_id=profile_id,
                langgraph_thread_id=None,
                created_at=now,
                updated_at=now,
            )
            self._records[application_id] = record
            return record

    def get_mapping(self, application_id: str) -> MappingRecord | None:
        with self._lock:
            return self._records.get(application_id)

    def assign_thread(self, application_id: str, langgraph_thread_id: str) -> MappingRecord:
        with self._lock:
            existing = self._records.get(application_id)
            if existing is None:
                raise MappingNotFoundError(application_id)
            if (
                existing.langgraph_thread_id is not None
                and existing.langgraph_thread_id != langgraph_thread_id
            ):
                raise MappingConflictError(application_id)
            updated = replace(
                existing,
                langgraph_thread_id=langgraph_thread_id,
                updated_at=datetime.now(UTC),
            )
            self._records[application_id] = updated
            return updated
