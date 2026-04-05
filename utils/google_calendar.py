"""
Google Calendar integration via Service Account.

The calendar sync uses explicit student mappings:
1. `student_id:<telegram_id>` in the event description.
2. Entries from `calendar_student_links`.

This avoids fuzzy name guessing and produces a detailed sync report.
"""
import asyncio
import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from data import config
from utils import runtime_store
from utils.timezone import DEFAULT_ACCOUNT_TIMEZONE, account_now, get_timezone, to_account_naive

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

logger = logging.getLogger(__name__)

LESSON_TITLE_MARKERS = (
    "урок с ",
    "урок со ",
    "ознакомительное занятие с ",
    "ознакомительное занятие со ",
)
LESSON_TITLE_STOP_WORDS = {
    "общий", "английский", "французский", "очно", "онлайн", "выезд",
    "для", "подготовка", "огэ", "егэ", "олимпиада", "экзамен",
    "урок", "занятие",
}


def _build_service():
    """Build the Google Calendar API service (synchronous)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_file = config.GOOGLE_CREDENTIALS_FILE
    if not os.path.exists(creds_file):
        raise FileNotFoundError(
            f"Файл Service Account JSON не найден: {creds_file}\n"
            "Проверьте путь в GOOGLE_CREDENTIALS_FILE и наличие ключа из Google Cloud Console."
        )

    credentials = service_account.Credentials.from_service_account_file(
        creds_file,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _fetch_events(days_ahead: int = 60) -> list[dict]:
    """Fetch upcoming events from Google Calendar (synchronous)."""
    service = _build_service()
    calendar_id = config.GOOGLE_CALENDAR_ID
    if not calendar_id:
        raise ValueError(
            "GOOGLE_CALENDAR_ID не задан в .env\n"
            "Укажите ID вашего календаря."
        )

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=2500,
    ).execute()
    return result.get("items", [])


def _delete_event(event_id: str) -> str:
    from googleapiclient.errors import HttpError

    service = _build_service()
    calendar_id = config.GOOGLE_CALENDAR_ID
    if not calendar_id:
        raise ValueError("GOOGLE_CALENDAR_ID не задан в .env")

    try:
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
        return "deleted"
    except HttpError as exc:
        if getattr(getattr(exc, "resp", None), "status", None) == 404:
            return "not_found"
        raise


async def delete_calendar_event(event_id: str) -> str:
    return await asyncio.to_thread(_delete_event, event_id)


def _normalize_text(value: str) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


def _event_summary(event: dict) -> str:
    return " ".join((event.get("summary", "") or "").split())


def _event_description(event: dict) -> str:
    return event.get("description", "") or ""


def _event_haystack(event: dict) -> tuple[str, str]:
    raw = f"{_event_summary(event)}\n{_event_description(event)}".strip()
    normalized = _normalize_text(raw)
    return raw, normalized


def _parse_event_student_id(event: dict) -> int | None:
    """
    Extract student telegram_id from an event description.
    Convention: add a line like `student_id:123456789` to the description.
    """
    description = _event_description(event)
    for line in description.splitlines():
        line = line.strip()
        if line.lower().startswith("student_id:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _calendar_sync_report_key(account_id: int | None) -> str:
    if account_id is None:
        return "calendar_sync_report"
    return f"calendar_sync_report:{int(account_id)}"


def _format_timezone_label(timezone_name: str | None) -> str:
    zone = get_timezone(timezone_name)
    return getattr(zone, "key", str(zone))


def _parse_event_start(event: dict, timezone_name: str | None) -> tuple[datetime | None, str | None]:
    """Parse event start time and normalize it to the account local wall clock."""
    start = event.get("start", {})
    if start.get("date") and not start.get("dateTime"):
        return None, "all_day_event"

    dt_str = start.get("dateTime")
    if not dt_str:
        return None, "missing_start"

    try:
        value = datetime.fromisoformat(dt_str)
    except ValueError:
        return None, "invalid_start"

    if value.tzinfo is None:
        event_timezone = (start.get("timeZone") or "").strip()
        if event_timezone:
            try:
                value = value.replace(tzinfo=ZoneInfo(event_timezone))
            except Exception:
                value = value.replace(tzinfo=get_timezone(timezone_name))
        else:
            value = value.replace(tzinfo=get_timezone(timezone_name))

    return to_account_naive(value, timezone_name), None


def _event_start_label(event: dict) -> str:
    return (
        event.get("start", {}).get("dateTime")
        or event.get("start", {}).get("date")
        or "—"
    )


def _build_link_matchers(links: list) -> tuple[list[dict], list[str]]:
    compiled = []
    warnings = []
    for row in links:
        alias = (row.get("calendar_alias") or "").strip()
        pattern = (row.get("calendar_event_pattern") or "").strip()
        compiled_pattern = None
        if pattern:
            try:
                compiled_pattern = re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                warnings.append(
                    f"Некорректный regex у {_event_safe_student_name(row)}: {pattern} ({exc})"
                )
        compiled.append(
            {
                "student_id": row["student_id"],
                "full_name": row["full_name"],
                "calendar_alias": alias,
                "calendar_alias_normalized": _normalize_text(alias),
                "calendar_event_pattern": pattern,
                "compiled_pattern": compiled_pattern,
            }
        )
    return compiled, warnings


def _event_safe_student_name(row) -> str:
    return row.get("full_name") or str(row.get("student_id"))


def _extract_lesson_subject_phrase(event: dict) -> str:
    summary = _normalize_text(_event_summary(event))
    for marker in LESSON_TITLE_MARKERS:
        if marker not in summary:
            continue
        tail = summary.split(marker, 1)[1].strip()
        if not tail:
            return ""
        words = []
        for token in tail.split():
            if token in LESSON_TITLE_STOP_WORDS:
                break
            words.append(token)
        return " ".join(words).strip()
    return ""


def _stem_name_token(token: str) -> str:
    value = _normalize_text(token)
    if len(value) <= 3:
        return value

    special_suffixes = (
        ("иями", 4),
        ("ями", 3),
        ("ами", 3),
        ("ыми", 3),
        ("ими", 3),
        ("ого", 3),
        ("ему", 3),
        ("ому", 3),
        ("ией", 2),
        ("ием", 2),
        ("ьей", 2),
        ("ей", 2),
        ("ой", 2),
        ("ую", 2),
        ("юю", 2),
        ("ым", 2),
        ("им", 2),
        ("ом", 2),
        ("ем", 2),
    )
    for suffix, trim in special_suffixes:
        if len(value) > len(suffix) + 1 and value.endswith(suffix):
            return value[:-trim]

    nominative_suffixes = (
        ("ий", 1),
        ("ый", 1),
        ("ой", 1),
        ("ия", 1),
        ("ья", 1),
        ("ая", 1),
        ("яя", 1),
    )
    for suffix, trim in nominative_suffixes:
        if len(value) > len(suffix) + 1 and value.endswith(suffix):
            return value[:-trim]

    endings = (
        "а", "я", "е", "у", "ю", "ы", "и",
    )
    for ending in endings:
        if len(value) > len(ending) + 2 and value.endswith(ending):
            return value[:-len(ending)]
    return value


def _token_variants(token: str) -> set[str]:
    value = _normalize_text(token)
    if not value:
        return set()

    variants = {value}
    stemmed = _stem_name_token(value)
    if stemmed:
        variants.add(stemmed)
    return variants


def _match_student_from_title(event: dict, students: list[dict]) -> tuple[int | None, str]:
    phrase = _extract_lesson_subject_phrase(event)
    if not phrase:
        return None, "no_title_person"

    phrase_tokens = [token for token in phrase.split() if token]
    phrase_variants = [_token_variants(token) for token in phrase_tokens if _token_variants(token)]
    if len(phrase_variants) < 2:
        return None, "title_person_too_short"

    matched_ids = set()
    for student in students:
        parts = [part for part in _normalize_text(student.get("full_name", "")).split() if part]
        if len(parts) < 2:
            continue

        matched_parts = 0
        for part in parts:
            student_variants = _token_variants(part)
            if student_variants and any(student_variants & phrase_token_variants for phrase_token_variants in phrase_variants):
                matched_parts += 1

        if matched_parts >= 2:
            matched_ids.add(student["telegram_id"])

    if not matched_ids:
        return None, "no_title_name_match"
    if len(matched_ids) > 1:
        return None, "ambiguous_title_name_match"
    return matched_ids.pop(), "title_full_name"


def _is_lesson_candidate(event: dict) -> tuple[bool, str]:
    explicit_student_id = _parse_event_student_id(event)
    if explicit_student_id is not None:
        return True, "student_id"

    summary_normalized = _normalize_text(_event_summary(event))
    if any(marker in summary_normalized for marker in LESSON_TITLE_MARKERS):
        return True, "lesson_title_marker"
    return False, "non_lesson_event"


def _match_student_from_links(event: dict, students_by_id: dict, links: list[dict]) -> tuple[int | None, str]:
    explicit_student_id = _parse_event_student_id(event)
    if explicit_student_id is not None:
        if explicit_student_id in students_by_id:
            return explicit_student_id, "student_id"
        return None, "student_id_not_found"

    raw_haystack, normalized_haystack = _event_haystack(event)
    matched_ids: set[int] = set()

    for link in links:
        alias = link["calendar_alias_normalized"]
        pattern = link["compiled_pattern"]

        if alias and alias in normalized_haystack:
            matched_ids.add(link["student_id"])
            continue
        if pattern and pattern.search(raw_haystack):
            matched_ids.add(link["student_id"])

    if not matched_ids:
        return None, "no_alias_match"
    if len(matched_ids) > 1:
        return None, "ambiguous_alias_match"
    return matched_ids.pop(), "alias"


async def _save_sync_report(report: dict, account_id: int | None):
    await runtime_store.write_document(_calendar_sync_report_key(account_id), report)


async def load_last_sync_report(account_id: int | None = None) -> dict:
    try:
        return await runtime_store.load_document(_calendar_sync_report_key(account_id))
    except Exception:
        return {}


def format_sync_report_html(report: dict, max_skipped: int = 10) -> str:
    if not report:
        return "📋 <b>Отчёт синхронизации Calendar</b>\n\nОтчёта пока нет."

    lines = [
        "📋 <b>Отчёт синхронизации Calendar</b>",
        "",
        f"🕒 Время: <b>{report.get('synced_at_local', '—')}</b>",
        f"📥 Событий из календаря: <b>{report.get('events_fetched', 0)}</b>",
        f"➕ Импортировано: <b>{report.get('imported', 0)}</b>",
        f"♻️ Обновлено: <b>{report.get('updated', 0)}</b>",
        f"🗑 Удалено из БД: <b>{report.get('deleted', 0)}</b>",
        f"⏭ Пропущено: <b>{report.get('skipped', 0)}</b>",
    ]

    warnings = report.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("⚠️ <b>Предупреждения:</b>")
        for item in warnings[:5]:
            lines.append(f"• {html.escape(item)}")

    missing_candidates = report.get("missing_student_candidates") or []
    if missing_candidates:
        lines.append("")
        lines.append("🧩 <b>Не найдены ученики из заголовков:</b>")
        for item in missing_candidates[:5]:
            lines.append(
                f"• <b>{html.escape(item.get('student_hint', '—'))}</b> — {item.get('count', 0)} событий"
            )
        if len(missing_candidates) > 5:
            lines.append(f"• … ещё {len(missing_candidates) - 5}")

    skipped_items = report.get("skipped_items") or []
    if skipped_items:
        lines.append("")
        lines.append("🚫 <b>Пропущенные события:</b>")
        for item in skipped_items[:max_skipped]:
            lines.append(
                f"• {html.escape(item.get('start', '—'))} — {html.escape(item.get('summary', 'Без названия'))} "
                f"(<i>{html.escape(item.get('reason', 'unknown'))}</i>)"
            )
        if len(skipped_items) > max_skipped:
            lines.append(f"• … ещё {len(skipped_items) - max_skipped}")

    return "\n".join(lines)


async def sync_calendar_to_db(db: "Database", days_ahead: int = 60) -> dict:
    """
    Fetch events from Google Calendar and sync them with explicit student links.

    Matching priority:
    1. `student_id:<telegram_id>` in event description.
    2. Active entries from `calendar_student_links`.
    """
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(None, lambda: _fetch_events(days_ahead))
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else None
    timezone_name = await db.get_account_timezone() if hasattr(db, "get_account_timezone") else DEFAULT_ACCOUNT_TIMEZONE
    reference_now = await db.get_account_now() if hasattr(db, "get_account_now") else datetime.now()
    local_now = account_now(timezone_name)

    students = await db.get_all_students()
    students_by_id = {student["telegram_id"]: student for student in students}
    links = await db.get_calendar_student_links()
    compiled_links, warnings = _build_link_matchers(links)

    report = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "synced_at_local": local_now.strftime("%d.%m.%Y %H:%M:%S ") + _format_timezone_label(timezone_name),
        "timezone": _format_timezone_label(timezone_name),
        "window_days": days_ahead,
        "events_fetched": len(events),
        "imported": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "warnings": warnings,
        "skipped_items": [],
        "missing_student_candidates": [],
    }
    missing_candidates: dict[str, dict] = {}

    calendar_event_ids = set()

    for event in events:
        google_event_id = event.get("id")
        summary = _event_summary(event) or "Без названия"
        if not google_event_id:
            report["skipped"] += 1
            report["skipped_items"].append(
                {"start": _event_start_label(event), "summary": summary, "reason": "missing_event_id"}
            )
            continue

        calendar_event_ids.add(google_event_id)

        is_lesson_candidate, candidate_reason = _is_lesson_candidate(event)
        if not is_lesson_candidate:
            report["skipped"] += 1
            report["skipped_items"].append(
                {"start": _event_start_label(event), "summary": summary, "reason": candidate_reason}
            )
            continue

        student_id, match_reason = _match_student_from_links(event, students_by_id, compiled_links)
        if not student_id:
            student_id, match_reason = _match_student_from_title(event, students)
        if not student_id:
            student_hint = _extract_lesson_subject_phrase(event)
            if match_reason in {"no_title_name_match", "title_person_too_short"} and student_hint:
                item = missing_candidates.setdefault(
                    student_hint,
                    {
                        "student_hint": student_hint,
                        "count": 0,
                        "examples": [],
                    },
                )
                item["count"] += 1
                if len(item["examples"]) < 3:
                    item["examples"].append(summary)
            report["skipped"] += 1
            report["skipped_items"].append(
                {
                    "start": _event_start_label(event),
                    "summary": summary,
                    "reason": match_reason,
                    "student_hint": student_hint or None,
                }
            )
            continue

        lesson_date, start_reason = _parse_event_start(event, timezone_name)
        if not lesson_date:
            report["skipped"] += 1
            report["skipped_items"].append(
                {"start": _event_start_label(event), "summary": summary, "reason": start_reason}
            )
            continue

        try:
            result = await db.upsert_lesson_from_calendar(student_id, google_event_id, lesson_date)
            if result == "inserted":
                report["imported"] += 1
            else:
                report["updated"] += 1
        except Exception as exc:
            logger.warning(f"Не удалось сохранить событие {google_event_id}: {exc}")
            report["skipped"] += 1
            report["skipped_items"].append(
                {"start": _event_start_label(event), "summary": summary, "reason": "db_error"}
            )

    db_event_ids = set(await db.get_google_event_ids_in_window(days_ahead, reference_now=reference_now))
    orphaned = db_event_ids - calendar_event_ids
    if orphaned:
        await db.delete_lessons_by_event_ids(list(orphaned))
        report["deleted"] = len(orphaned)

    report["missing_student_candidates"] = sorted(
        missing_candidates.values(),
        key=lambda item: (-item["count"], item["student_hint"]),
    )

    await _save_sync_report(report, account_id)
    logger.info(
        "Google Calendar sync: fetched=%s imported=%s updated=%s skipped=%s deleted=%s",
        report["events_fetched"],
        report["imported"],
        report["updated"],
        report["skipped"],
        report["deleted"],
    )
    return report
