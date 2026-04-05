from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from utils import runtime_store


def storage_key_to_string(key: StorageKey) -> str:
    thread_id = key.thread_id if key.thread_id is not None else "-"
    business_id = key.business_connection_id or "-"
    destiny = key.destiny or "default"
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{thread_id}:{business_id}:{destiny}"


class JsonFileStorage(BaseStorage):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _storage_key(self, key: StorageKey) -> str:
        return storage_key_to_string(key)

    def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_unlocked(self, payload: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        async with self._lock:
            payload = self._load_unlocked()
            storage_key = self._storage_key(key)
            record = payload.get(storage_key, {"state": None, "data": {}})
            record["state"] = state_value
            if state_value is None and not record.get("data"):
                payload.pop(storage_key, None)
            else:
                payload[storage_key] = record
            self._save_unlocked(payload)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._lock:
            payload = self._load_unlocked()
            record = payload.get(self._storage_key(key), {})
            return record.get("state")

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            storage_key = self._storage_key(key)
            record = payload.get(storage_key, {"state": None, "data": {}})
            record["data"] = dict(data)
            if record.get("state") is None and not record["data"]:
                payload.pop(storage_key, None)
            else:
                payload[storage_key] = record
            self._save_unlocked(payload)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._lock:
            payload = self._load_unlocked()
            record = payload.get(self._storage_key(key), {})
            return dict(record.get("data") or {})

    async def update_data(self, key: StorageKey, data: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            payload = self._load_unlocked()
            storage_key = self._storage_key(key)
            record = payload.get(storage_key, {"state": None, "data": {}})
            current = dict(record.get("data") or {})
            current.update(data)
            record["data"] = current
            if record.get("state") is None and not current:
                payload.pop(storage_key, None)
            else:
                payload[storage_key] = record
            self._save_unlocked(payload)
            return dict(current)

    async def close(self) -> None:
        return None


class PostgresStorage(BaseStorage):
    def _storage_key(self, key: StorageKey) -> str:
        return storage_key_to_string(key)

    async def _load_record(self, key: StorageKey) -> dict[str, Any]:
        return await runtime_store.load_fsm_record(self._storage_key(key))

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        record = await self._load_record(key)
        await runtime_store.upsert_fsm_record(
            self._storage_key(key),
            state_value,
            dict(record.get("data") or {}),
        )

    async def get_state(self, key: StorageKey) -> str | None:
        record = await self._load_record(key)
        return record.get("state")

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        record = await self._load_record(key)
        await runtime_store.upsert_fsm_record(
            self._storage_key(key),
            record.get("state"),
            dict(data or {}),
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record = await self._load_record(key)
        return dict(record.get("data") or {})

    async def update_data(self, key: StorageKey, data: dict[str, Any]) -> dict[str, Any]:
        record = await self._load_record(key)
        current = dict(record.get("data") or {})
        current.update(data or {})
        await runtime_store.upsert_fsm_record(
            self._storage_key(key),
            record.get("state"),
            current,
        )
        return dict(current)

    async def close(self) -> None:
        return None
