from app.repositories.in_memory_mapping_repository import InMemoryMappingRepository
from app.services.session_service import SessionService


class InMemoryLangGraphClient:
    def __init__(self) -> None:
        self.calls = 0

    async def health(self) -> bool:
        return True

    async def create_thread(self, application_id: str) -> str:
        self.calls += 1
        return f"thread_for_{application_id}"

    async def status_snapshot(self) -> dict[str, str]:
        return {"status": "ok"}

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


async def test_session_service_resolves_thread_once() -> None:
    repository = InMemoryMappingRepository()
    client = InMemoryLangGraphClient()
    service = SessionService(
        repository=repository,
        langgraph_client=client,
        application_id_prefix="app",
    )

    session = await service.create_session(profile_id="profile-a")
    first = await service.ensure_thread(session.application_id)
    second = await service.ensure_thread(session.application_id)

    assert first.langgraph_thread_id is not None
    assert first.langgraph_thread_id == second.langgraph_thread_id
    assert client.calls == 1
