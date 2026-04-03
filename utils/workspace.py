from __future__ import annotations


WORKSPACE_ROLE_LABELS = {
    "owner": "Владелец",
    "manager": "Менеджер",
    "assistant": "Ассистент",
    "student": "Ученик",
    "parent": "Родитель",
}

INVITE_PAYLOAD_PREFIX = "join_"


def workspace_role_label(role: str | None) -> str:
    value = (role or "").strip().lower()
    return WORKSPACE_ROLE_LABELS.get(value, value or "Пользователь")


def extract_start_payload(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    parts = raw.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def build_invite_payload(token: str) -> str:
    return f"{INVITE_PAYLOAD_PREFIX}{token}"


def extract_invite_token(payload: str | None) -> str | None:
    value = (payload or "").strip()
    if not value:
        return None
    if value.startswith(INVITE_PAYLOAD_PREFIX):
        token = value[len(INVITE_PAYLOAD_PREFIX):].strip()
        return token or None
    if value.startswith("invite_"):
        token = value.split("_", 1)[1].strip()
        return token or None
    return None


def build_invite_start_link(bot_username: str | None, token: str) -> str:
    payload = build_invite_payload(token)
    username = (bot_username or "").strip().lstrip("@")
    if username:
        return f"https://t.me/{username}?start={payload}"
    return f"/start {payload}"
