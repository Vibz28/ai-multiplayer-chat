from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.config import get_settings
from app.dependencies import (
    get_langgraph_client,
    get_mapping_repository,
    get_session_service,
    get_websocket_hub,
)
from app.event_schema import normalize_event
from app.models import (
    HealthCheckResponse,
    SessionCreateRequest,
    SessionResponse,
    ThreadResponse,
    WebSocketInboundMessage,
)
from app.repositories.mapping_repository import MappingNotFoundError
from app.services.langgraph_client import LangGraphClientError
from app.services.session_service import SessionService
from app.services.websocket_hub import WebSocketHub


@asynccontextmanager
async def lifespan(application: FastAPI):
    repository_provider = application.dependency_overrides.get(
        get_mapping_repository,
        get_mapping_repository,
    )
    repository = repository_provider()
    await run_in_threadpool(repository.ensure_table)
    yield


settings = get_settings()
app = FastAPI(title=settings.api_title, lifespan=lifespan)


def _session_response(record) -> SessionResponse:
    return SessionResponse(
        application_id=record.application_id,
        profile_id=record.profile_id,
        langgraph_thread_id=record.langgraph_thread_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/health", response_model=HealthCheckResponse)
async def health(
    repository=Depends(get_mapping_repository),
    langgraph_client=Depends(get_langgraph_client),
) -> HealthCheckResponse:
    dynamodb_ok = False
    try:
        dynamodb_ok = await run_in_threadpool(repository.ping)
    except Exception:
        dynamodb_ok = False

    langgraph_ok = await langgraph_client.health()
    overall_ok = dynamodb_ok and langgraph_ok

    return HealthCheckResponse(
        status="ok" if overall_ok else "degraded",
        checks={
            "dynamodb": dynamodb_ok,
            "langgraph": langgraph_ok,
        },
    )


@app.post("/v1/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    created = await service.create_session(profile_id=request.profile_id)
    return _session_response(created)


@app.get("/v1/sessions/{application_id}", response_model=SessionResponse)
async def get_session(
    application_id: str,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = await service.get_session(application_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_response(session)


@app.post("/v1/sessions/{application_id}/thread", response_model=ThreadResponse)
async def resolve_thread(
    application_id: str,
    service: SessionService = Depends(get_session_service),
) -> ThreadResponse:
    try:
        mapping = await service.ensure_thread(application_id)
    except MappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except LangGraphClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if mapping.langgraph_thread_id is None:
        raise HTTPException(status_code=500, detail="Thread resolution failed")

    return ThreadResponse(
        application_id=mapping.application_id,
        langgraph_thread_id=mapping.langgraph_thread_id,
        updated_at=mapping.updated_at,
    )


@app.websocket("/ws/{application_id}")
async def websocket_chat(
    application_id: str,
    websocket: WebSocket,
    service: SessionService = Depends(get_session_service),
    hub: WebSocketHub = Depends(get_websocket_hub),
) -> None:
    existing = await service.get_session(application_id)
    if existing is None:
        await websocket.close(code=1008, reason="Unknown application_id")
        return

    await hub.connect(application_id, websocket)
    try:
        await hub.emit(
            application_id,
            normalize_event(
                event_type="connection",
                application_id=application_id,
                thread_id=existing.langgraph_thread_id,
                stream_state="connected",
                payload={"message": "connected"},
            ),
        )

        while True:
            payload = await websocket.receive_json()
            try:
                inbound = WebSocketInboundMessage.model_validate(payload)
            except ValidationError as exc:
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="error",
                        application_id=application_id,
                        payload={"message": "Invalid payload", "details": exc.errors()},
                    ),
                )
                continue

            if inbound.type == "ping":
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="status",
                        application_id=application_id,
                        thread_id=existing.langgraph_thread_id,
                        stream_state="idle",
                        payload={"message": "pong"},
                    ),
                )
                continue

            if not inbound.content:
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="error",
                        application_id=application_id,
                        payload={"message": "content is required for user_message"},
                    ),
                )
                continue

            try:
                mapping = await service.ensure_thread(application_id)
            except LangGraphClientError as exc:
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="error",
                        application_id=application_id,
                        payload={"message": str(exc)},
                    ),
                )
                continue

            await hub.emit(
                application_id,
                normalize_event(
                    event_type="status",
                    application_id=application_id,
                    thread_id=mapping.langgraph_thread_id,
                    stream_state="generating",
                    payload={"message": "queued"},
                ),
            )
            await hub.emit(
                application_id,
                normalize_event(
                    event_type="reasoning",
                    application_id=application_id,
                    thread_id=mapping.langgraph_thread_id,
                    stream_state="reasoning",
                    payload={
                        "delta": "Phase 1 placeholder reasoning path acknowledged request and reserved event channels."
                    },
                ),
            )
            await hub.emit(
                application_id,
                normalize_event(
                    event_type="content",
                    application_id=application_id,
                    thread_id=mapping.langgraph_thread_id,
                    stream_state="generating",
                    payload={
                        "delta": (
                            "Phase 1 foundation response: backend routing, session mapping, "
                            "and thread continuity plumbing are active."
                        )
                    },
                ),
            )
            await hub.emit(
                application_id,
                normalize_event(
                    event_type="complete",
                    application_id=application_id,
                    thread_id=mapping.langgraph_thread_id,
                    stream_state="completed",
                    payload={"message": "completed"},
                ),
            )
    except WebSocketDisconnect:
        await hub.disconnect(application_id, websocket)
