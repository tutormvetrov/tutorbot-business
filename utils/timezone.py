from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_ACCOUNT_TIMEZONE = "Europe/Moscow"
UTC = timezone.utc


def get_timezone(name: str | None) -> ZoneInfo:
    candidate = (name or "").strip() or DEFAULT_ACCOUNT_TIMEZONE
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_ACCOUNT_TIMEZONE)


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


def account_now(timezone_name: str | None) -> datetime:
    return utc_now().astimezone(get_timezone(timezone_name))


def account_now_naive(timezone_name: str | None) -> datetime:
    return account_now(timezone_name).replace(tzinfo=None)


def account_today(timezone_name: str | None) -> date:
    return account_now(timezone_name).date()


def localize_account_naive(value: datetime, timezone_name: str | None) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(get_timezone(timezone_name))
    return value.replace(tzinfo=get_timezone(timezone_name))


def to_account_naive(value: datetime, timezone_name: str | None) -> datetime:
    return localize_account_naive(value, timezone_name).replace(tzinfo=None)


def to_utc_naive(value: datetime, timezone_name: str | None) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_timezone(timezone_name))
    return value.astimezone(UTC).replace(tzinfo=None)
