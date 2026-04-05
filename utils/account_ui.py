from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from data.config import load_ui_seed_defaults
from utils.brand import DEFAULT_BRAND_TONE, normalize_brand_tone

UI_MENU_SECTION_LABELS = {
    "client_main": "Клиентское меню",
    "parent_main": "Меню родителя",
    "owner_main": "Меню владельца",
    "manager_main": "Меню менеджера",
    "assistant_main": "Меню ассистента",
    "admin_account": "Админ: аккаунт",
    "admin_system": "Админ: система",
    "admin_service": "Админ: сервис",
}

UI_PREVIEW_ROLES = {
    "student": "Ученик",
    "parent": "Родитель",
    "manager": "Менеджер",
    "assistant": "Ассистент",
    "owner": "Владелец",
}


def resolve_ui_payload(snapshot_or_payload: dict | None) -> dict:
    if not snapshot_or_payload:
        return load_ui_seed_defaults()
    if isinstance(snapshot_or_payload, dict) and "resolved" in snapshot_or_payload:
        return deepcopy(snapshot_or_payload.get("resolved") or load_ui_seed_defaults())
    return deepcopy(snapshot_or_payload)


def ui_branding(payload: dict | None) -> dict:
    resolved = resolve_ui_payload(payload)
    return dict(resolved.get("branding") or {})


def ui_contacts(payload: dict | None) -> dict:
    resolved = resolve_ui_payload(payload)
    return dict(resolved.get("contacts") or {})


def ui_requisites(payload: dict | None) -> dict:
    resolved = resolve_ui_payload(payload)
    return dict(resolved.get("requisites") or {})


def ui_copy(payload: dict | None) -> dict:
    resolved = resolve_ui_payload(payload)
    return dict(resolved.get("copy") or {})


def ui_display_name(payload: dict | None, fallback: str = "TutorScalebot") -> str:
    return str(ui_branding(payload).get("display_name") or fallback).strip() or fallback


def ui_tone(payload: dict | None) -> str:
    return normalize_brand_tone(ui_branding(payload).get("tone") or DEFAULT_BRAND_TONE)


def ui_copy_text(payload: dict | None, key: str, fallback: str = "") -> str:
    value = ui_copy(payload).get(key)
    return str(value or fallback).strip() or fallback


def build_teacher_info_from_ui(payload: dict | None) -> dict:
    resolved = resolve_ui_payload(payload)
    contacts = ui_contacts(payload)
    requisites = ui_requisites(payload)
    return {
        "contacts": contacts,
        "requisites": requisites,
        "reschedule": dict(resolved.get("reschedule") or {}),
        "project_site_url": contacts.get("project_site_url", ""),
        "level_test_url": contacts.get("level_test_url", ""),
    }


def menu_section_for_role(role: str | None, is_platform_admin: bool = False) -> str:
    normalized = (role or "").strip().lower()
    if normalized == "parent":
        return "parent_main"
    if is_platform_admin or normalized == "owner":
        return "owner_main"
    if normalized == "manager":
        return "manager_main"
    if normalized == "assistant":
        return "assistant_main"
    return "client_main"


def get_menu_entries(payload: dict | None, section: str, *, include_disabled: bool = True) -> list[dict]:
    resolved = resolve_ui_payload(payload)
    menu = resolved.get("menu") or {}
    entries = deepcopy(menu.get(section) or [])
    entries.sort(key=lambda item: (int(item.get("order", 999)), str(item.get("label") or "").lower()))
    if include_disabled:
        return entries
    return [item for item in entries if item.get("enabled", True)]


def get_main_menu_entries(
    payload: dict | None,
    role: str | None,
    *,
    is_platform_admin: bool = False,
    include_disabled: bool = False,
) -> list[dict]:
    section = menu_section_for_role(role, is_platform_admin=is_platform_admin)
    return get_menu_entries(payload, section, include_disabled=include_disabled)


def find_menu_entry(payload: dict | None, section: str, item_id: str) -> dict | None:
    for item in get_menu_entries(payload, section):
        if str(item.get("id")) == str(item_id):
            return item
    return None


def replace_menu_section(payload: dict | None, section: str, entries: list[dict]) -> dict:
    resolved = resolve_ui_payload(payload)
    menu = dict(resolved.get("menu") or {})
    normalized = []
    for index, item in enumerate(entries, start=1):
        row = dict(item)
        row["order"] = index
        normalized.append(row)
    menu[section] = normalized
    resolved["menu"] = menu
    return resolved


def build_ui_update(section: str, field: str, value: Any) -> dict:
    return {section: {field: value}}


def make_custom_menu_item_id(entries: list[dict]) -> str:
    existing = {str(item.get("id")) for item in entries}
    index = 1
    while True:
        candidate = f"custom_{index}"
        if candidate not in existing:
            return candidate
        index += 1


def validate_custom_menu_url(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("Ссылка не должна быть пустой.")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if parsed.netloc in {"t.me", "telegram.me"}:
            return value, "telegram_url"
        return value, "url"
    if value.startswith("tg://"):
        return value, "telegram_url"
    raise ValueError("Разрешены только http/https ссылки и Telegram-ссылки.")
