from datetime import datetime

from aiogram import Router, html, types
from aiogram.filters import StateFilter

from keyboards.inline import make_back_button_keyboard
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import load_ops_status, load_recent_runtime_events
from utils.ui_text import ADMIN_HEALTH_NO_ERRORS_TEXT
from utils.workspace import has_workspace_admin_access

router = Router()


def _is_admin(user_id: int) -> bool:
    return has_workspace_admin_access(user_id)


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(value)


def _format_job_line(label: str, job: dict | None, metric_keys: tuple[str, ...] = ()) -> str:
    if not job:
        return f"• {label}: <b>нет данных</b>"

    metric_labels = {
        "sent": "отправлено",
        "checked": "проверено",
        "unpaid": "без оплаты",
        "paid": "с оплатой",
        "completed": "завершено",
        "imported": "импортировано",
        "updated": "обновлено",
        "deleted": "удалено",
        "skipped": "пропущено",
    }
    fragments = [f"• {label}: <b>{html.quote(str(job.get('status', 'unknown')))}</b>"]
    updated_at = _format_timestamp(job.get("updated_at"))
    if updated_at != "—":
        fragments.append(f"({updated_at})")

    metrics = []
    for key in metric_keys:
        if key in job:
            metric_label = metric_labels.get(key, key)
            metrics.append(f"{metric_label}: {html.quote(str(job[key]))}")
    if metrics:
        fragments.append("· " + ", ".join(metrics))
    return " ".join(fragments)


def _format_health_text(student_count: int, report: dict, ops_status: dict, runtime_events: list[dict]) -> str:
    status = ops_status.get("status", "unknown")
    scheduler = ops_status.get("scheduler", "unknown")
    jobs = ops_status.get("jobs") or {}
    last_sync = report.get("synced_at_local") or _format_timestamp(ops_status.get("last_calendar_sync"))
    errors = [event for event in runtime_events if event.get("status") == "error"]

    lines = [
        "🏥 <b>Здоровье бота</b>",
        "",
        "Общее:",
        f"🤖 Статус: <b>{html.quote(str(status))}</b>",
        f"⏱ Scheduler: <b>{html.quote(str(scheduler))}</b>",
        f"👥 Активных учеников: <b>{student_count}</b>",
        "",
        "Calendar sync:",
        f"🗓 Последний sync: <b>{html.quote(str(last_sync))}</b>",
        f"📥 Импортировано: <b>{report.get('imported', 0)}</b>",
        f"♻️ Обновлено: <b>{report.get('updated', 0)}</b>",
        f"🗑 Удалено: <b>{report.get('deleted', 0)}</b>",
        f"⏭ Пропущено: <b>{report.get('skipped', 0)}</b>",
        "",
        "🔔 <b>Планировщик напоминаний</b>",
        _format_job_line("Уроки", jobs.get("lesson_reminder"), ("sent", "checked")),
        _format_job_line("Домашка", jobs.get("homework_reminder"), ("sent",)),
        _format_job_line("Оплата (утро)", jobs.get("payment_reminder_morning"), ("unpaid", "paid")),
        _format_job_line("Оплата (вечер)", jobs.get("payment_reminder_evening"), ("unpaid", "paid")),
    ]

    if errors:
        lines.append("")
        lines.append("⚠️ <b>Последние ошибки jobs:</b>")
        for event in errors[-5:]:
            happened_at = _format_timestamp(event.get("ts"))
            lines.append(
                f"• {html.quote(event.get('event_type', 'unknown'))} — {html.quote(event.get('status', 'unknown'))}"
                + (f" ({html.quote(happened_at)})" if happened_at != "—" else "")
            )
    else:
        lines.append("")
        lines.append(ADMIN_HEALTH_NO_ERRORS_TEXT)

    return "\n".join(lines)


@router.callback_query(lambda c: c.data == 'admin:health', StateFilter('*'))
async def admin_health(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = await db.get_all_students()
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else None
    report = await load_last_sync_report(account_id)
    ops_status = await load_ops_status()
    runtime_events = await load_recent_runtime_events(limit=30)

    text = _format_health_text(len(students), report, ops_status, runtime_events)
    await callback_query.message.edit_text(
        text,
        reply_markup=make_back_button_keyboard("◀️ К системе", "admin:cat:system"),
    )
    await callback_query.answer()
