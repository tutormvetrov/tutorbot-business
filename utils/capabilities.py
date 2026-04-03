from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from data.config import load_product_config


PLAN_CAPABILITY_MATRIX: dict[str, dict[str, Any]] = {
    "start": {
        "capabilities": {
            "students_core": True,
            "lessons_core": True,
            "payments_core": True,
            "homework_core": True,
            "manual_messages": True,
            "reminders": True,
            "calendar_sync": False,
            "smart_reschedule": False,
            "weekly_digest": False,
            "segmented_broadcasts": False,
            "groups": False,
            "analytics_lite": False,
            "analytics_plus": False,
            "team_roles": False,
            "priority_features": False,
        },
        "limits": {
            "active_students": 25,
            "groups": 0,
            "team_members": 1,
        },
    },
    "practice": {
        "capabilities": {
            "students_core": True,
            "lessons_core": True,
            "payments_core": True,
            "homework_core": True,
            "manual_messages": True,
            "reminders": True,
            "calendar_sync": True,
            "smart_reschedule": True,
            "weekly_digest": True,
            "segmented_broadcasts": True,
            "groups": True,
            "analytics_lite": True,
            "analytics_plus": False,
            "team_roles": False,
            "priority_features": False,
        },
        "limits": {
            "active_students": 80,
            "groups": 12,
            "team_members": 1,
        },
    },
    "studio": {
        "capabilities": {
            "students_core": True,
            "lessons_core": True,
            "payments_core": True,
            "homework_core": True,
            "manual_messages": True,
            "reminders": True,
            "calendar_sync": True,
            "smart_reschedule": True,
            "weekly_digest": True,
            "segmented_broadcasts": True,
            "groups": True,
            "analytics_lite": True,
            "analytics_plus": True,
            "team_roles": True,
            "priority_features": True,
        },
        "limits": {
            "active_students": None,
            "groups": None,
            "team_members": 5,
        },
    },
}

CAPABILITY_LABELS: dict[str, str] = {
    "calendar_sync": "Google Calendar sync",
    "smart_reschedule": "умный перенос",
    "weekly_digest": "weekly digest для родителей",
    "segmented_broadcasts": "сегментные рассылки",
    "groups": "группы",
    "analytics_lite": "analytics lite",
    "analytics_plus": "analytics plus",
    "team_roles": "командные роли",
    "priority_features": "приоритетные функции",
}

CAPABILITY_ORDER = [
    "calendar_sync",
    "smart_reschedule",
    "weekly_digest",
    "segmented_broadcasts",
    "groups",
    "analytics_lite",
    "analytics_plus",
    "team_roles",
    "priority_features",
]

TRIAL_STATUS_LABELS = {
    "trial": "trial активен",
    "trial_expired": "trial завершён",
    "active": "подписка активна",
    "expired": "подписка истекла",
    "inactive": "подписка не активирована",
}


def normalize_plan_code(value: str | None) -> str:
    code = (value or "").strip().lower()
    return code if code in PLAN_CAPABILITY_MATRIX else "start"


def capability_label(capability: str) -> str:
    return CAPABILITY_LABELS.get(capability, capability.replace("_", " "))


def get_trial_defaults() -> tuple[str, int]:
    product = load_product_config()
    return (
        normalize_plan_code(product.get("trial_plan")),
        int(product.get("trial_days", 14) or 14),
    )


def build_default_trial_window(now: datetime | None = None) -> tuple[str, datetime]:
    trial_plan, trial_days = get_trial_defaults()
    current_time = now or datetime.now()
    return trial_plan, current_time + timedelta(days=trial_days)


@dataclass(slots=True)
class ResolvedSubscription:
    account_id: int | None
    plan_code: str
    effective_plan_code: str
    raw_status: str
    effective_status: str
    trial_ends_at: datetime | None
    paid_until: datetime | None
    overrides: dict[str, bool]
    capabilities: dict[str, bool]
    limits: dict[str, int | None]

    @property
    def locked_capabilities(self) -> list[str]:
        return [
            capability
            for capability in CAPABILITY_ORDER
            if not self.capabilities.get(capability, False)
        ]

    @property
    def is_trial_active(self) -> bool:
        return self.effective_status == "trial"

    @property
    def is_paid_active(self) -> bool:
        return self.effective_status == "active"


def resolve_subscription(
    subscription: dict[str, Any] | None,
    overrides: dict[str, bool] | None = None,
    now: datetime | None = None,
) -> ResolvedSubscription:
    current_time = now or datetime.now()
    trial_plan, trial_ends_at_default = build_default_trial_window(now=current_time)
    payload = subscription or {}
    plan_code = normalize_plan_code(payload.get("plan_code") or trial_plan)
    raw_status = (payload.get("status") or "trial").strip().lower()
    trial_ends_at = payload.get("trial_ends_at") or trial_ends_at_default
    paid_until = payload.get("paid_until")

    if raw_status == "trial":
        if trial_ends_at and trial_ends_at >= current_time:
            effective_status = "trial"
            effective_plan_code = plan_code
        else:
            effective_status = "trial_expired"
            effective_plan_code = "start"
    elif raw_status == "active":
        if paid_until and paid_until >= current_time:
            effective_status = "active"
            effective_plan_code = plan_code
        else:
            effective_status = "expired"
            effective_plan_code = "start"
    else:
        effective_status = "inactive"
        effective_plan_code = "start"

    base_matrix = PLAN_CAPABILITY_MATRIX[effective_plan_code]
    capability_map = dict(base_matrix["capabilities"])
    limits = dict(base_matrix["limits"])
    override_map = dict(overrides or {})
    for capability, enabled in override_map.items():
        capability_map[capability] = bool(enabled)

    return ResolvedSubscription(
        account_id=payload.get("account_id"),
        plan_code=plan_code,
        effective_plan_code=effective_plan_code,
        raw_status=raw_status,
        effective_status=effective_status,
        trial_ends_at=trial_ends_at,
        paid_until=paid_until,
        overrides=override_map,
        capabilities=capability_map,
        limits=limits,
    )


def limit_label(value: int | None, unlimited_text: str = "без лимита") -> str:
    return unlimited_text if value is None else str(value)
