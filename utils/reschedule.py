from __future__ import annotations

from datetime import datetime, timedelta, time

DEFAULT_RESCHEDULE_CONFIG = {
    "window_days": 14,
    "slot_count": 3,
    "lesson_duration_minutes": 90,
    "slot_step_minutes": 30,
    "min_lead_hours": 12,
    "weekly_windows": {
        "0": [["10:00", "20:00"]],
        "1": [["10:00", "20:00"]],
        "2": [["10:00", "20:00"]],
        "3": [["10:00", "20:00"]],
        "4": [["10:00", "20:00"]],
        "5": [["11:00", "17:00"]],
    },
}


def _parse_hhmm(value: str) -> time:
    hour_str, minute_str = value.split(":")
    return time(hour=int(hour_str), minute=int(minute_str))


def load_reschedule_config(info: dict | None = None) -> dict:
    info = info or {}
    payload = dict(DEFAULT_RESCHEDULE_CONFIG)
    payload.update(info.get("reschedule", {}))
    payload["weekly_windows"] = info.get("reschedule", {}).get(
        "weekly_windows",
        DEFAULT_RESCHEDULE_CONFIG["weekly_windows"],
    )
    return payload


def format_reschedule_slot_label(slot: datetime) -> str:
    return slot.strftime("%d.%m %H:%M")


def encode_reschedule_slot(slot: datetime) -> str:
    return slot.strftime("%Y%m%d%H%M")


def decode_reschedule_slot(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M")


def _round_up(value: datetime, step_minutes: int) -> datetime:
    minute_bucket = ((value.minute // step_minutes) + (1 if value.minute % step_minutes else 0)) * step_minutes
    rounded = value.replace(second=0, microsecond=0)
    if minute_bucket >= 60:
        rounded = rounded.replace(minute=0) + timedelta(hours=1)
    else:
        rounded = rounded.replace(minute=minute_bucket)
    return rounded


async def find_next_free_reschedule_slots(db, now: datetime | None = None, info: dict | None = None) -> list[datetime]:
    config = load_reschedule_config(info)
    now = now or datetime.now()
    search_from = _round_up(now + timedelta(hours=config["min_lead_hours"]), config["slot_step_minutes"])
    search_until = search_from + timedelta(days=config["window_days"])
    duration = timedelta(minutes=config["lesson_duration_minutes"])
    step = timedelta(minutes=config["slot_step_minutes"])

    busy_lessons = await db.get_lessons_in_window(search_from, search_until)
    busy_ranges = [
        (lesson["lesson_date"], lesson["lesson_date"] + duration)
        for lesson in busy_lessons
        if lesson.get("lesson_date")
    ]

    def is_free(candidate: datetime) -> bool:
        candidate_end = candidate + duration
        for busy_start, busy_end in busy_ranges:
            if candidate < busy_end and candidate_end > busy_start:
                return False
        return True

    slots: list[datetime] = []
    cursor = search_from
    weekly_windows = config["weekly_windows"]

    while cursor <= search_until and len(slots) < config["slot_count"]:
        day_windows = weekly_windows.get(str(cursor.weekday()), [])
        for start_label, end_label in day_windows:
            window_start = datetime.combine(cursor.date(), _parse_hhmm(start_label))
            window_end = datetime.combine(cursor.date(), _parse_hhmm(end_label))
            candidate = max(_round_up(window_start, config["slot_step_minutes"]), search_from)
            while candidate + duration <= window_end and len(slots) < config["slot_count"]:
                if is_free(candidate):
                    slots.append(candidate)
                candidate += step
        cursor = datetime.combine((cursor + timedelta(days=1)).date(), time(0, 0))

    return slots
