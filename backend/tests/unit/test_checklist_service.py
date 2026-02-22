from app.repositories.in_memory_mapping_repository import InMemoryMappingRepository
from app.services.checklist_service import CanonicalChecklistService
from app.services.langgraph_client import ThreadChecklistItem
from app.services.session_service import SessionService


class InMemoryLangGraphClient:
    async def health(self) -> bool:
        return True

    async def create_thread(self, application_id: str) -> str:
        return f"thread_for_{application_id}"

    async def get_thread_history(self, *, thread_id: str, limit: int = 200):
        return []

    async def get_thread_checklist(self, *, thread_id: str):
        return [
            ThreadChecklistItem(index=1, text=f"prepare answer for {thread_id}", done=True),
            ThreadChecklistItem(index=2, text='finalize response', done=False),
        ]

    async def status_snapshot(self) -> dict[str, str]:
        return {'status': 'ok'}

    async def stream_agent_run(
        self,
        *,
        application_id: str,
        thread_id: str,
        profile_id: str | None,
        message: str,
    ):
        if False:
            yield {}


async def test_checklist_service_reads_thread_scoped_items() -> None:
    repository = InMemoryMappingRepository()
    client = InMemoryLangGraphClient()
    session_service = SessionService(
        repository=repository,
        langgraph_client=client,
        application_id_prefix='app',
    )
    checklist_service = CanonicalChecklistService(
        mapping_repository=repository,
        langgraph_client=client,
    )

    session = await session_service.create_session(profile_id='profile-a', role='member')
    resolved = await session_service.ensure_thread(session.application_id)

    response = await checklist_service.get_application_checklist(application_id=session.application_id)

    assert response.application_id == session.application_id
    assert response.langgraph_thread_id == resolved.langgraph_thread_id
    assert response.count == 2
    assert response.items[0].done is True
    assert response.items[1].done is False
