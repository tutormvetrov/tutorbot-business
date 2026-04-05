from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import asyncpg
from asyncpg import Connection
from asyncpg.pool import Pool

from data import config


logger = logging.getLogger(__name__)


def _json_payload(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
    return value


class RuntimeStore:
    def __init__(self):
        self._pool: Pool | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _build_search_path(self) -> str:
        schema = (config.PGSCHEMA or "public").strip()
        if schema == "public":
            return "public"
        return f'{self._quote_identifier(schema)}, public'

    async def _ensure_operational_schema(self):
        schema = (config.PGSCHEMA or "public").strip()
        if not schema or schema == "public":
            return
        connection = await asyncpg.connect(
            user=config.PGUSER,
            password=config.PGPASSWORD,
            host=config.PGHOST,
            port=int(config.PGPORT),
            database=config.DATABASE,
        )
        try:
            await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)};")
        finally:
            await connection.close()

    async def _init_connection(self, connection: Connection):
        await connection.execute(f"SET search_path TO {self._build_search_path()};")
        await connection.execute("SET TIME ZONE 'UTC';")

    async def _ensure_tables(self):
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_documents (
                        key TEXT PRIMARY KEY,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_events (
                        id BIGSERIAL PRIMARY KEY,
                        ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        event_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb
                    );
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_fsm_states (
                        storage_key TEXT PRIMARY KEY,
                        state TEXT,
                        data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_job_runs (
                        account_id INTEGER NOT NULL,
                        job_name TEXT NOT NULL,
                        run_key TEXT NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (account_id, job_name, run_key)
                    );
                    """
                )
                await connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS runtime_events_ts_idx
                    ON runtime_events (ts DESC);
                    """
                )

    async def _ensure_pool(self) -> Pool:
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            await self._ensure_operational_schema()
            try:
                self._pool = await asyncpg.create_pool(
                    user=config.PGUSER,
                    password=config.PGPASSWORD,
                    host=config.PGHOST,
                    port=int(config.PGPORT),
                    database=config.DATABASE,
                    init=self._init_connection,
                )
                await self._ensure_tables()
            except Exception:
                if self._pool is not None:
                    await self._pool.close()
                    self._pool = None
                raise
            return self._pool

    async def write_document(self, key: str, payload: Any) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO runtime_documents (key, payload, updated_at)
                VALUES ($1, $2::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET payload = EXCLUDED.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                key,
                json.dumps(_json_payload(payload), ensure_ascii=False),
            )

    async def merge_document(self, key: str, payload: dict[str, Any]) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO runtime_documents (key, payload, updated_at)
                VALUES ($1, $2::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET payload = COALESCE(runtime_documents.payload, '{}'::jsonb) || EXCLUDED.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                key,
                json.dumps(dict(payload or {}), ensure_ascii=False),
            )

    async def load_document(self, key: str) -> dict[str, Any]:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT payload
                FROM runtime_documents
                WHERE key = $1
                """,
                key,
            )
        if not row:
            return {}
        payload = row["payload"]
        if isinstance(payload, str):
            return _json_payload(payload)
        return dict(payload or {})

    async def load_documents(self, prefix: str) -> dict[str, dict[str, Any]]:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT key, payload
                FROM runtime_documents
                WHERE key LIKE $1
                ORDER BY key
                """,
                f"{prefix}%",
            )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, str):
                result[row["key"]] = _json_payload(payload)
            else:
                result[row["key"]] = dict(payload or {})
        return result

    async def append_event(self, event_type: str, status: str, payload: dict[str, Any] | None = None) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO runtime_events (event_type, status, payload)
                VALUES ($1, $2, $3::jsonb)
                """,
                event_type,
                status,
                json.dumps(dict(payload or {}), ensure_ascii=False),
            )

    async def load_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT ts, event_type, status, payload
                FROM runtime_events
                ORDER BY ts DESC, id DESC
                LIMIT $1
                """,
                int(limit),
            )
        items: list[dict[str, Any]] = []
        for row in reversed(rows):
            payload = row["payload"]
            if isinstance(payload, str):
                payload = _json_payload(payload)
            items.append(
                {
                    "ts": row["ts"].isoformat(),
                    "event_type": row["event_type"],
                    "status": row["status"],
                    **dict(payload or {}),
                }
            )
        return items

    async def load_fsm_record(self, storage_key: str) -> dict[str, Any]:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT state, data
                FROM runtime_fsm_states
                WHERE storage_key = $1
                """,
                storage_key,
            )
        if not row:
            return {}
        data = row["data"]
        if isinstance(data, str):
            data = _json_payload(data)
        return {
            "state": row["state"],
            "data": dict(data or {}),
        }

    async def upsert_fsm_record(self, storage_key: str, state: str | None, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        if state is None and not payload:
            await self.delete_fsm_record(storage_key)
            return
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO runtime_fsm_states (storage_key, state, data, updated_at)
                VALUES ($1, $2, $3::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (storage_key) DO UPDATE
                SET state = EXCLUDED.state,
                    data = EXCLUDED.data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                storage_key,
                state,
                json.dumps(payload, ensure_ascii=False),
            )

    async def delete_fsm_record(self, storage_key: str) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                DELETE FROM runtime_fsm_states
                WHERE storage_key = $1
                """,
                storage_key,
            )

    async def claim_job_run(
        self,
        account_id: int,
        job_name: str,
        run_key: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            result = await connection.fetchval(
                """
                INSERT INTO runtime_job_runs (account_id, job_name, run_key, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT DO NOTHING
                RETURNING 1
                """,
                int(account_id),
                job_name,
                run_key,
                json.dumps(dict(payload or {}), ensure_ascii=False),
            )
        return bool(result)

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None


_store = RuntimeStore()


async def write_document(key: str, payload: Any) -> None:
    await _store.write_document(key, payload)


async def merge_document(key: str, payload: dict[str, Any]) -> None:
    await _store.merge_document(key, payload)


async def load_document(key: str) -> dict[str, Any]:
    return await _store.load_document(key)


async def load_documents(prefix: str) -> dict[str, dict[str, Any]]:
    return await _store.load_documents(prefix)


async def append_event(event_type: str, status: str, payload: dict[str, Any] | None = None) -> None:
    await _store.append_event(event_type, status, payload=payload)


async def load_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    return await _store.load_recent_events(limit=limit)


async def load_fsm_record(storage_key: str) -> dict[str, Any]:
    return await _store.load_fsm_record(storage_key)


async def upsert_fsm_record(storage_key: str, state: str | None, data: dict[str, Any]) -> None:
    await _store.upsert_fsm_record(storage_key, state, data)


async def delete_fsm_record(storage_key: str) -> None:
    await _store.delete_fsm_record(storage_key)


async def claim_job_run(
    account_id: int,
    job_name: str,
    run_key: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    return await _store.claim_job_run(account_id, job_name, run_key, payload=payload)


async def close_runtime_store() -> None:
    await _store.close()
