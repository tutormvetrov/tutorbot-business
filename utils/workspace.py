from __future__ import annotations

from contextvars import ContextVar

from data import config

WORKSPACE_ROLE_LABELS = {
    "owner": "Владелец",
    "manager": "Менеджер",
    "assistant": "Ассистент",
    "student": "Ученик",
    "parent": "Родитель",
}

INVITE_PAYLOAD_PREFIX = "join_"
WORKSPACE_ADMIN_ROLES = {"owner", "manager"}
WORKSPACE_TEAM_ROLES = {"owner", "manager"}
WORKSPACE_STAFF_ROLES = {"owner", "manager", "assistant"}

_workspace_role_var: ContextVar[str | None] = ContextVar("workspace_role", default=None)
_workspace_account_user_var: ContextVar[dict | None] = ContextVar("workspace_account_user", default=None)
_workspace_account_var: ContextVar[dict | None] = ContextVar("workspace_account", default=None)
_workspace_identity_var: ContextVar[dict | None] = ContextVar("workspace_identity", default=None)


def workspace_role_label(role: str | None) -> str:
    value = (role or "").strip().lower()
    return WORKSPACE_ROLE_LABELS.get(value, value or "Пользователь")


def push_workspace_context(account: dict | None, account_user: dict | None, identity: dict | None) -> dict:
    return {
        "role": _workspace_role_var.set((account_user or {}).get("role")),
        "account_user": _workspace_account_user_var.set(account_user),
        "account": _workspace_account_var.set(account),
        "identity": _workspace_identity_var.set(identity),
    }


def reset_workspace_context(tokens: dict | None):
    if not tokens:
        return
    _workspace_role_var.reset(tokens["role"])
    _workspace_account_user_var.reset(tokens["account_user"])
    _workspace_account_var.reset(tokens["account"])
    _workspace_identity_var.reset(tokens["identity"])


def current_workspace_role() -> str | None:
    return _workspace_role_var.get()


def current_workspace_account_user() -> dict | None:
    return _workspace_account_user_var.get()


def current_workspace_account() -> dict | None:
    return _workspace_account_var.get()


def current_workspace_identity() -> dict | None:
    return _workspace_identity_var.get()


def has_workspace_role(user_id: int, *roles: str, allow_platform_admin: bool = True) -> bool:
    if allow_platform_admin and user_id == config.ADMIN_ID:
        return True
    current_role = (current_workspace_role() or "").strip().lower()
    allowed = {role.strip().lower() for role in roles if role}
    return bool(current_role and current_role in allowed)


def has_workspace_admin_access(user_id: int) -> bool:
    return has_workspace_role(user_id, *WORKSPACE_ADMIN_ROLES)


def has_workspace_team_access(user_id: int) -> bool:
    return has_workspace_role(user_id, *WORKSPACE_TEAM_ROLES)


def has_workspace_staff_access(user_id: int) -> bool:
    return has_workspace_role(user_id, *WORKSPACE_STAFF_ROLES)


def has_workspace_billing_access(user_id: int) -> bool:
    return has_workspace_role(user_id, "owner")


def has_workspace_support_access(user_id: int) -> bool:
    return has_workspace_role(user_id, "owner", "manager")


def has_workspace_manager_invite_access(user_id: int) -> bool:
    return has_workspace_role(user_id, "owner")


def has_workspace_assistant_invite_access(user_id: int) -> bool:
    return has_workspace_role(user_id, "owner", "manager")


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
