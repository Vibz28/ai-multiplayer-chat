from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import websockets

LOGGER = logging.getLogger("fieldwork.telegram")
STATE_PATH = Path("/data/rooms.json")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    backend_http_url: str
    backend_ws_url: str
    frontend_public_url: str
    transcription_api_key: str
    transcription_model: str
    harness: str

    @classmethod
    def from_env(cls) -> Settings:
        allowed = frozenset(
            int(value.strip())
            for value in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
            if value.strip()
        )
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        if not allowed:
            raise RuntimeError("TELEGRAM_ALLOWED_CHAT_IDS must contain at least one chat ID")
        return cls(
            bot_token=token,
            allowed_chat_ids=allowed,
            backend_http_url=os.environ.get("BACKEND_HTTP_URL", "http://backend:8000").rstrip("/"),
            backend_ws_url=os.environ.get("BACKEND_WS_URL", "ws://backend:8000").rstrip("/"),
            frontend_public_url=os.environ.get("FRONTEND_PUBLIC_URL", "http://localhost:5173").rstrip("/"),
            transcription_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            transcription_model=os.environ.get(
                "TELEGRAM_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"
            ),
            harness=os.environ.get("TELEGRAM_HARNESS", "langgraph"),
        )


class TelegramGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram_url = f"https://api.telegram.org/bot{settings.bot_token}"
        self.telegram_file_url = f"https://api.telegram.org/file/bot{settings.bot_token}"
        self.client = httpx.AsyncClient(timeout=45)
        self.rooms = self._load_rooms()
        self.room_locks: dict[str, asyncio.Lock] = {}
        self.run_locks: dict[str, asyncio.Lock] = {}
        self.update_tasks: set[asyncio.Task[None]] = set()

    @staticmethod
    def _load_rooms() -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_rooms(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.rooms, indent=2), encoding="utf-8")
        temporary.replace(STATE_PATH)

    async def telegram(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.post(f"{self.telegram_url}/{method}", json=payload or {})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Telegram {method} returned HTTP {exc.response.status_code}") from None
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} failed")
        return body.get("result")

    async def send_text(self, chat_id: int, text: str) -> None:
        clean = text.strip() or "The worker finished without a written update."
        for start in range(0, len(clean), 3900):
            await self.telegram("sendMessage", {"chat_id": chat_id, "text": clean[start : start + 3900]})

    async def ensure_room(self, chat_id: int) -> dict[str, str]:
        key = str(chat_id)
        lock = self.room_locks.setdefault(key, asyncio.Lock())
        async with lock:
            existing = self.rooms.get(key)
            if existing:
                response = await self.client.get(
                    f"{self.settings.backend_http_url}/v1/sessions/"
                    f"{existing['application_id']}",
                    headers={"Authorization": f"Bearer {existing['room_token']}"},
                )
                if response.is_success:
                    return existing
                self.rooms.pop(key, None)

            response = await self.client.post(
                f"{self.settings.backend_http_url}/v1/sessions",
                json={"profile_id": f"telegram-{chat_id}", "role": "collaborator"},
            )
            response.raise_for_status()
            created = response.json()
            room = {
                "application_id": created["application_id"],
                "room_token": created["room_token"],
            }
            thread = await self.client.post(
                f"{self.settings.backend_http_url}/v1/sessions/"
                f"{room['application_id']}/thread",
                headers={"Authorization": f"Bearer {room['room_token']}"},
            )
            thread.raise_for_status()
            self.rooms[key] = room
            self._save_rooms()
            return room

    async def room_link(self, chat_id: int) -> str:
        room = await self.ensure_room(chat_id)
        room_id = quote(room["application_id"], safe="")
        room_token = quote(room["room_token"], safe="")
        return f"{self.settings.frontend_public_url}/#room={room_id}&key={room_token}"

    async def transcribe_voice(self, file_id: str) -> str:
        if not self.settings.transcription_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for cloud voice transcription")
        file_info = await self.telegram("getFile", {"file_id": file_id})
        file_path = str(file_info["file_path"])
        try:
            response = await self.client.get(f"{self.telegram_file_url}/{file_path}")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Telegram file download returned HTTP {exc.response.status_code}"
            ) from None

        transcription = await self.client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.settings.transcription_api_key}"},
            data={"model": self.settings.transcription_model},
            files={
                "file": (
                    Path(file_path).name or "voice.oga",
                    response.content,
                    response.headers.get("content-type", "audio/ogg"),
                )
            },
        )
        transcription.raise_for_status()
        return str(transcription.json().get("text", "")).strip()

    async def run_worker(self, chat_id: int, sender: str, prompt: str) -> str:
        room = await self.ensure_room(chat_id)
        lock = self.run_locks.setdefault(str(chat_id), asyncio.Lock())
        async with lock:
            request_id = str(uuid4())
            socket_url = f"{self.settings.backend_ws_url}/ws/{room['application_id']}"
            response_parts: list[str] = []
            async with websockets.connect(
                socket_url,
                subprotocols=[f"fieldwork.{room['room_token']}"],
                open_timeout=20,
            ) as socket:
                await socket.send(
                    json.dumps({"type": "join", "profile_id": sender, "role": "collaborator"})
                )
                while True:
                    event = json.loads(await asyncio.wait_for(socket.recv(), timeout=20))
                    if event.get("type") == "connection":
                        break

                await socket.send(
                    json.dumps(
                        {
                            "type": "user_message",
                            "content": prompt,
                            "profile_id": sender,
                            "role": "collaborator",
                            "include_ai": True,
                            "delivery_mode": "thread",
                            "recipient_profile_ids": [],
                            "harness": self.settings.harness,
                            "client_request_id": request_id,
                        }
                    )
                )
                while True:
                    event = json.loads(await asyncio.wait_for(socket.recv(), timeout=900))
                    event_type = event.get("type")
                    payload = event.get("payload") or {}
                    if payload.get("client_request_id") != request_id:
                        continue
                    if event_type == "content":
                        response_parts.append(str(payload.get("delta", "")))
                    elif event_type == "error":
                        raise RuntimeError(str(payload.get("message", "The worker could not finish.")))
                    elif event_type == "complete":
                        return "".join(response_parts)

    async def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return
        if chat_id not in self.settings.allowed_chat_ids:
            LOGGER.warning("Rejected Telegram chat ID %s", chat_id)
            return

        sender_info = message.get("from") or {}
        sender = sender_info.get("first_name") or sender_info.get("username") or "Phone"
        text = str(message.get("text") or message.get("caption") or "").strip()

        if text in {"/start", "/room"}:
            link = await self.room_link(chat_id)
            await self.send_text(
                chat_id,
                "Moss is ready. Send a message or voice note here, or open the shared workroom:\n" + link,
            )
            return

        voice = message.get("voice")
        if isinstance(voice, dict) and voice.get("file_id"):
            await self.send_text(chat_id, "I am listening to your voice note now.")
            text = await self.transcribe_voice(str(voice["file_id"]))
            if not text:
                await self.send_text(chat_id, "I could not make out that voice note. Please try again.")
                return

        if not text:
            await self.send_text(chat_id, "Send a written message or an iPhone voice note to assign work.")
            return

        await self.send_text(chat_id, "Got it. Moss is working on that now.")
        try:
            result = await self.run_worker(chat_id, str(sender), text)
            await self.send_text(chat_id, result)
        except Exception:
            LOGGER.exception("Worker run failed for chat %s", chat_id)
            await self.send_text(chat_id, "Moss could not finish that request. The workroom has the details.")

    async def handle_update_safely(self, update: dict[str, Any]) -> None:
        try:
            await self.handle_update(update)
        except Exception:
            LOGGER.exception("Telegram update %s failed", update.get("update_id"))

    async def run(self) -> None:
        offset = 0
        LOGGER.info("Telegram gateway started with %d approved chat(s)", len(self.settings.allowed_chat_ids))
        while True:
            try:
                updates = await self.telegram(
                    "getUpdates",
                    {"offset": offset, "timeout": 30, "allowed_updates": ["message", "channel_post"]},
                )
                for update in updates:
                    offset = max(offset, int(update["update_id"]) + 1)
                    task = asyncio.create_task(self.handle_update_safely(update))
                    self.update_tasks.add(task)
                    task.add_done_callback(self.update_tasks.discard)
            except Exception:
                LOGGER.exception("Telegram polling failed")
                await asyncio.sleep(3)


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    gateway = TelegramGateway(Settings.from_env())
    try:
        await gateway.run()
    finally:
        await gateway.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
