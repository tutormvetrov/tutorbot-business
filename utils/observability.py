from __future__ import annotations

import logging
from datetime import datetime, timezone

from utils import runtime_store


logger = logging.getLogger(__name__)

OPS_STATUS_KEY = "ops_status"
OPS_JOB_PREFIX = "ops_job:"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def write_runtime_event(event_type: str, status: str, **payload):
    record = dict(payload or {})
    try:
        await runtime_store.append_event(event_type, status, payload=record)
    except Exception as exc:
        logger.warning("Не удалось записать runtime event %s/%s: %s", event_type, status, exc)


async def update_ops_status(**payload):
    record = {
        **dict(payload or {}),
        "updated_at": _utc_timestamp(),
    }
    try:
        await runtime_store.merge_document(OPS_STATUS_KEY, record)
    except Exception as exc:
        logger.warning("Не удалось обновить ops status: %s", exc)


async def update_job_status(job_name: str, status: str, **payload):
    record = {
        "status": status,
        "updated_at": _utc_timestamp(),
        **dict(payload or {}),
    }
    try:
        await runtime_store.write_document(f"{OPS_JOB_PREFIX}{job_name}", record)
        await update_ops_status()
    except Exception as exc:
        logger.warning("Не удалось обновить статус job %s: %s", job_name, exc)


async def load_ops_status() -> dict:
    try:
        payload = await runtime_store.load_document(OPS_STATUS_KEY)
        jobs = {}
        for key, value in (await runtime_store.load_documents(OPS_JOB_PREFIX)).items():
            jobs[key.removeprefix(OPS_JOB_PREFIX)] = value
        if jobs:
            payload["jobs"] = jobs
        return payload
    except Exception as exc:
        logger.warning("Не удалось прочитать ops status: %s", exc)
        return {}


async def load_recent_runtime_events(limit: int = 20) -> list[dict]:
    try:
        return await runtime_store.load_recent_events(limit=limit)
    except Exception as exc:
        logger.warning("Не удалось прочитать runtime events: %s", exc)
        return []
