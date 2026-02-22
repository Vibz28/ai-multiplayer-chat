from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from app.agent import get_compiled_graph
from app.config import get_settings


class RuntimeState:
    def __init__(self) -> None:
        self.postgres_pool: asyncpg.Pool | None = None
        self.redis_client: Redis | None = None
        self.agent_graph: Any | None = None


state = RuntimeState()
settings = get_settings()


async def _ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                application_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_events (
                id BIGSERIAL PRIMARY KEY,
                application_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                profile_id TEXT,
                role TEXT NOT NULL,
                channel TEXT NOT NULL,
                content TEXT NOT NULL,
                run_id TEXT,
                trace_id TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_thread_events_thread_created
            ON thread_events(thread_id, created_at)
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.postgres_pool = await asyncpg.create_pool(dsn=settings.postgres_dsn)
    state.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    state.agent_graph = get_compiled_graph()

    await _ensure_schema(state.postgres_pool)
    await state.redis_client.ping()

    yield

    if state.redis_client is not None:
        await state.redis_client.aclose()
    if state.postgres_pool is not None:
        await state.postgres_pool.close()


async def postgres_healthy() -> bool:
    if state.postgres_pool is None:
        return False
    try:
        async with state.postgres_pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
        return True
    except Exception:
        return False


async def redis_healthy() -> bool:
    if state.redis_client is None:
        return False
    try:
        await state.redis_client.ping()
        return True
    except Exception:
        return False
