from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.config import get_settings
from app.dependencies import (
    get_checklist_service,
    get_history_service,
    get_langgraph_client,
    get_mapping_repository,
    get_session_service,
    get_websocket_hub,
)
from app.event_schema import normalize_event
from app.models import (
    HealthCheckResponse,
    SessionChecklistResponse,
    SessionCreateRequest,
    SessionHistoryResponse,
    SessionResponse,
    ThreadResponse,
    WebSocketInboundMessage,
)
from app.repositories.mapping_repository import MappingNotFoundError
from app.services.history_service import CanonicalHistoryService
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
        role=record.role,
        langgraph_thread_id=record.langgraph_thread_id,
        workflow_id=record.workflow_id,
        langsmith_trace_id=record.langsmith_trace_id,
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
    created = await service.create_session(
        profile_id=request.profile_id,
        role=request.role,
    )
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
        workflow_id=mapping.workflow_id,
        langsmith_trace_id=mapping.langsmith_trace_id,
        updated_at=mapping.updated_at,
    )


@app.get("/v1/sessions/{application_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    application_id: str,
    limit: int = 200,
    history_service: CanonicalHistoryService = Depends(get_history_service),
) -> SessionHistoryResponse:
    try:
        return await history_service.get_application_history(
            application_id=application_id,
            limit=limit,
        )
    except MappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session or thread not found") from exc
    except LangGraphClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/sessions/{application_id}/checklist", response_model=SessionChecklistResponse)
async def get_session_checklist(
    application_id: str,
    checklist_service=Depends(get_checklist_service),
) -> SessionChecklistResponse:
    try:
        return await checklist_service.get_application_checklist(application_id=application_id)
    except MappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session or thread not found") from exc
    except LangGraphClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.websocket("/ws/{application_id}")
async def websocket_chat(
    application_id: str,
    websocket: WebSocket,
    service: SessionService = Depends(get_session_service),
    hub: WebSocketHub = Depends(get_websocket_hub),
    repository=Depends(get_mapping_repository),
    langgraph_client=Depends(get_langgraph_client),
) -> None:
    existing = await service.get_session(application_id)
    if existing is None:
        await websocket.close(code=1008, reason="Unknown application_id")
        return

    default_profile = existing.profile_id or "anonymous"
    default_role = existing.role or "member"
    await hub.connect(application_id, websocket)
    participant = await hub.set_participant(
        application_id,
        websocket,
        profile_id=default_profile,
        role=default_role,
    )
    try:
        participants = await hub.participants_snapshot(application_id)
        await hub.emit(
            application_id,
            normalize_event(
                event_type="connection",
                application_id=application_id,
                thread_id=existing.langgraph_thread_id,
                stream_state="connected",
                payload={
                    "message": "connected",
                    "profile_id": participant.profile_id,
                    "role": participant.role,
                    "participants": participants,
                },
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

            if inbound.type == "join":
                participant = await hub.set_participant(
                    application_id,
                    websocket,
                    profile_id=inbound.profile_id or participant.profile_id,
                    role=inbound.role or participant.role,
                )
                participants = await hub.participants_snapshot(application_id)
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="participant_join",
                        application_id=application_id,
                        thread_id=existing.langgraph_thread_id,
                        stream_state="idle",
                        payload={
                            "profile_id": participant.profile_id,
                            "role": participant.role,
                            "participants": participants,
                        },
                    ),
                )
                continue

            if inbound.type == "leave":
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="participant_leave",
                        application_id=application_id,
                        thread_id=existing.langgraph_thread_id,
                        stream_state="idle",
                        payload={
                            "profile_id": participant.profile_id,
                            "role": participant.role,
                            "message": "participant requested disconnect",
                        },
                    ),
                )
                break

            if inbound.type == "ping":
                try:
                    snapshot = await langgraph_client.status_snapshot()
                except LangGraphClientError:
                    snapshot = {"status": "unreachable"}
                participants = await hub.participants_snapshot(application_id)
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="status",
                        application_id=application_id,
                        thread_id=existing.langgraph_thread_id,
                        stream_state="idle",
                        payload={
                            "message": "pong",
                            "snapshot": snapshot,
                            "participants": participants,
                        },
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

            participant = await hub.set_participant(
                application_id,
                websocket,
                profile_id=inbound.profile_id or participant.profile_id,
                role=inbound.role or participant.role,
            )
            sender_profile = participant.profile_id
            sender_role = participant.role
            recipient_profiles = {
                profile_id.strip()
                for profile_id in inbound.recipient_profile_ids
                if profile_id and profile_id.strip()
            }
            is_direct = inbound.delivery_mode == "direct" and bool(recipient_profiles)
            target_profiles = set(recipient_profiles)
            target_profiles.add(sender_profile)

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

            user_message_event = normalize_event(
                event_type="user_message",
                application_id=application_id,
                thread_id=mapping.langgraph_thread_id,
                stream_state="idle",
                payload={
                    "content": inbound.content,
                    "profile_id": sender_profile,
                    "role": sender_role,
                    "include_ai": inbound.include_ai,
                    "delivery_mode": inbound.delivery_mode,
                    "recipient_profile_ids": sorted(recipient_profiles),
                },
            )
            if is_direct:
                await hub.emit_to_profiles(
                    application_id,
                    user_message_event,
                    profile_ids=target_profiles,
                )
            else:
                await hub.emit(application_id, user_message_event)

            if not inbound.include_ai:
                continue

            if await hub.generation_busy(application_id):
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="status",
                        application_id=application_id,
                        thread_id=mapping.langgraph_thread_id,
                        stream_state="generating",
                        payload={
                            "message": "queued_for_agent",
                            "profile_id": sender_profile,
                            "delivery_mode": inbound.delivery_mode,
                        },
                    ),
                )

            async with hub.generation_guard(application_id):
                await hub.emit(
                    application_id,
                    normalize_event(
                        event_type="status",
                        application_id=application_id,
                        thread_id=mapping.langgraph_thread_id,
                        stream_state="generating",
                        payload={
                            "message": "agent_run_started",
                            "profile_id": sender_profile,
                            "delivery_mode": inbound.delivery_mode,
                        },
                    ),
                )
                try:
                    preflight = await langgraph_client.status_snapshot()
                    await hub.emit(
                        application_id,
                        normalize_event(
                            event_type="status",
                            application_id=application_id,
                            thread_id=mapping.langgraph_thread_id,
                            stream_state="generating",
                            payload={
                                "message": "langgraph_preflight",
                                "snapshot": preflight,
                                "profile_id": sender_profile,
                            },
                        ),
                    )
                except LangGraphClientError:
                    await hub.emit(
                        application_id,
                        normalize_event(
                            event_type="status",
                            application_id=application_id,
                            thread_id=mapping.langgraph_thread_id,
                            stream_state="generating",
                            payload={
                                "message": "langgraph_preflight_failed",
                                "profile_id": sender_profile,
                            },
                        ),
                    )

                try:
                    async for upstream_event in langgraph_client.stream_agent_run(
                        application_id=application_id,
                        thread_id=mapping.langgraph_thread_id,
                        profile_id=sender_profile,
                        message=inbound.content,
                    ):
                        upstream_type = str(upstream_event.get("type", "status"))
                        upstream_state = str(upstream_event.get("stream_state", "generating"))
                        upstream_payload = upstream_event.get("payload", {})
                        if not isinstance(upstream_payload, dict):
                            upstream_payload = {"value": upstream_payload}
                        upstream_payload.setdefault("initiated_by_profile_id", sender_profile)
                        upstream_payload.setdefault("delivery_mode", inbound.delivery_mode)
                        upstream_payload.setdefault(
                            "recipient_profile_ids",
                            sorted(recipient_profiles),
                        )

                        run_payload = upstream_payload.get("run")
                        if isinstance(run_payload, dict):
                            workflow_id = run_payload.get("run_id")
                            trace_id = run_payload.get("trace_id")
                            safe_workflow = workflow_id if isinstance(workflow_id, str) else None
                            safe_trace = trace_id if isinstance(trace_id, str) else None
                            if safe_workflow is not None or safe_trace is not None:
                                try:
                                    await run_in_threadpool(
                                        repository.upsert_workflow_metadata,
                                        application_id,
                                        safe_workflow,
                                        safe_trace,
                                    )
                                except Exception:
                                    pass

                        stream_event = normalize_event(
                            event_type=upstream_type,
                            application_id=application_id,
                            thread_id=mapping.langgraph_thread_id,
                            stream_state=upstream_state,
                            payload=upstream_payload,
                        )
                        if is_direct:
                            await hub.emit_to_profiles(
                                application_id,
                                stream_event,
                                profile_ids=target_profiles,
                            )
                        else:
                            await hub.emit(application_id, stream_event)
                except LangGraphClientError as exc:
                    await hub.emit(
                        application_id,
                        normalize_event(
                            event_type="error",
                            application_id=application_id,
                            thread_id=mapping.langgraph_thread_id,
                            stream_state="error",
                            payload={"message": str(exc)},
                        ),
                    )
                    continue
    except WebSocketDisconnect:
        await hub.emit(
            application_id,
            normalize_event(
                event_type="participant_leave",
                application_id=application_id,
                thread_id=existing.langgraph_thread_id,
                stream_state="idle",
                payload={
                    "profile_id": participant.profile_id,
                    "role": participant.role,
                    "message": "disconnected",
                },
            ),
        )
    finally:
        await hub.disconnect(application_id, websocket)
