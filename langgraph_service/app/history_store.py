from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.runtime import state


async def persist_history_entry(
    *,
    application_id: str,
    thread_id: str,
    profile_id: str | None,
    role: str,
    channel: str,
    content: str,
    run_id: str | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> None:
    captured_at = created_at or datetime.now(UTC)
    metadata_payload = metadata or {}

    if state.postgres_pool is not None:
        try:
            async with state.postgres_pool.acquire() as connection:
                await connection.execute(
                    """
                    INSERT INTO thread_events(
                        application_id, thread_id, profile_id, role, channel,
                        content, run_id, trace_id, metadata, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
                    """,
                    application_id,
                    thread_id,
                    profile_id,
                    role,
                    channel,
                    content,
                    run_id,
                    trace_id,
                    json.dumps(metadata_payload),
                    captured_at,
                )
        except Exception:
            pass

    if state.redis_client is not None:
        try:
            key = f"thread:{thread_id}:history"
            entry = {
                "application_id": application_id,
                "thread_id": thread_id,
                "profile_id": profile_id,
                "role": role,
                "channel": channel,
                "content": content,
                "run_id": run_id,
                "trace_id": trace_id,
                "metadata": metadata_payload,
                "created_at": captured_at.isoformat(),
            }
            await state.redis_client.rpush(key, json.dumps(entry))
            await state.redis_client.ltrim(key, -500, -1)
            await state.redis_client.set(
                f"thread:{thread_id}:last_seen",
                captured_at.isoformat(),
            )
        except Exception:
            pass


async def fetch_thread_history(thread_id: str, limit: int = 200) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 1000))
    collected: list[dict[str, Any]] = []

    if state.postgres_pool is not None:
        try:
            async with state.postgres_pool.acquire() as connection:
                rows = await connection.fetch(
                    """
                    SELECT application_id, thread_id, profile_id, role, channel,
                           content, run_id, trace_id, metadata, created_at
                    FROM thread_events
                    WHERE thread_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    thread_id,
                    bounded_limit,
                )
            for row in reversed(rows):
                metadata_value = row["metadata"] if isinstance(row["metadata"], dict) else {}
                collected.append(
                    {
                        "application_id": str(row["application_id"]),
                        "thread_id": str(row["thread_id"]),
                        "profile_id": row["profile_id"],
                        "role": str(row["role"]),
                        "channel": str(row["channel"]),
                        "content": str(row["content"]),
                        "run_id": row["run_id"],
                        "trace_id": row["trace_id"],
                        "metadata": metadata_value,
                        "created_at": row["created_at"],
                    }
                )
        except Exception:
            collected = []

    if collected:
        return collected

    if state.redis_client is None:
        return []

    try:
        payloads = await state.redis_client.lrange(f"thread:{thread_id}:history", -bounded_limit, -1)
    except Exception:
        return []

    for raw in payloads:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        created_raw = entry.get("created_at")
        created_at = datetime.now(UTC)
        if isinstance(created_raw, str):
            try:
                created_at = datetime.fromisoformat(created_raw)
            except ValueError:
                created_at = datetime.now(UTC)

        metadata_value = entry.get("metadata")
        if not isinstance(metadata_value, dict):
            metadata_value = {}

        collected.append(
            {
                "application_id": str(entry.get("application_id", "")),
                "thread_id": str(entry.get("thread_id", thread_id)),
                "profile_id": entry.get("profile_id"),
                "role": str(entry.get("role", "system")),
                "channel": str(entry.get("channel", "event")),
                "content": str(entry.get("content", "")),
                "run_id": entry.get("run_id"),
                "trace_id": entry.get("trace_id"),
                "metadata": metadata_value,
                "created_at": created_at,
            }
        )

    return collected
