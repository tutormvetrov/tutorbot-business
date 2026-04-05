import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from data import config
from utils.account_ui import build_teacher_info_from_ui, resolve_ui_payload, ui_tone
from keyboards.inline import (
    make_lesson_presence_keyboard,
    make_teacher_reply_keyboard,
)
from utils.brand import choose_tone_variant
from utils.observability import update_job_status, update_ops_status, write_runtime_event
from utils.reschedule import encode_reschedule_slot, find_next_free_reschedule_slots, format_reschedule_slot_label
from utils.speech import choose_form
from utils.timezone import account_now
from utils.ui_text import build_parent_weekly_digest_text

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

logger = logging.getLogger(__name__)
LOCAL_JOB_WINDOW_MINUTES = 15


def _is_single_account_scheduler_run(db: "Database") -> bool:
    return bool(getattr(db, "_scheduler_single_account_mode", False))


def _should_emit_scheduler_metrics(db: "Database") -> bool:
    return not _is_single_account_scheduler_run(db) and hasattr(db, "pool")


async def _operator_recipient_ids(db: "Database") -> list[int]:
    if hasattr(db, "get_account_operator_chat_ids"):
        return await db.get_account_operator_chat_ids()
    if config.ADMIN_ID:
        return [config.ADMIN_ID]
    return []


async def _run_scheduler_across_accounts(
    db: "Database",
    job_name: str,
    job_runner,
):
    if _is_single_account_scheduler_run(db) or not hasattr(db, "list_active_accounts"):
        return None
    accounts = await db.list_active_accounts()
    if not accounts:
        return {"accounts": 0}

    aggregate: dict[str, int] = {"accounts": 0, "errors": 0}
    previous_flag = getattr(db, "_scheduler_single_account_mode", False)
    for account in accounts:
        token = db.push_account_context(account["id"])
        setattr(db, "_scheduler_single_account_mode", True)
        try:
            result = await job_runner(dict(account))
            aggregate["accounts"] += 1
            if isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, bool):
                        aggregate[key] = aggregate.get(key, 0) + int(value)
                    elif isinstance(value, int):
                        aggregate[key] = aggregate.get(key, 0) + value
        except Exception as exc:
            aggregate["errors"] += 1
            logger.exception("Scheduler job %s failed for account %s: %s", job_name, account.get("id"), exc)
        finally:
            db.reset_account_context(token)
            setattr(db, "_scheduler_single_account_mode", previous_flag)
    return aggregate


async def _get_scheduler_ui_payload(db: "Database") -> dict:
    if hasattr(db, "get_resolved_ui_config"):
        return resolve_ui_payload(await db.get_resolved_ui_config(db.require_account_id()))
    return {}


async def _account_reference_now(db: "Database") -> datetime:
    if hasattr(db, "get_account_now"):
        return await db.get_account_now()
    return datetime.now()


async def _account_local_now(db: "Database") -> datetime:
    timezone_name = await db.get_account_timezone() if hasattr(db, "get_account_timezone") else "UTC"
    return account_now(timezone_name)


async def _call_with_reference(method, reference_now: datetime):
    try:
        return await method(reference_now=reference_now)
    except TypeError as exc:
        if "reference_now" not in str(exc):
            raise
        return await method()


async def _claim_local_job_window(
    db: "Database",
    job_name: str,
    *,
    hour: int,
    minute: int = 0,
    weekday: int | None = None,
    window_minutes: int = LOCAL_JOB_WINDOW_MINUTES,
) -> tuple[bool, datetime]:
    if not hasattr(db, "get_account_timezone") and not hasattr(db, "get_account_now"):
        return True, datetime.now()

    local_now = await _account_local_now(db)
    if weekday is not None and local_now.weekday() != weekday:
        return False, local_now

    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta_minutes = (local_now - target).total_seconds() / 60
    if delta_minutes < 0 or delta_minutes >= window_minutes:
        return False, local_now

    if not hasattr(db, "require_account_id"):
        return True, local_now

    from utils import runtime_store

    run_key = local_now.strftime("%Y-%m-%d")
    claimed = await runtime_store.claim_job_run(
        db.require_account_id(),
        job_name,
        run_key,
        payload={"local_ts": local_now.isoformat()},
    )
    return claimed, local_now


def _get_online_lesson_links(ui_payload: dict | None) -> tuple[str, str]:
    info = build_teacher_info_from_ui(ui_payload)
    contacts = info.get("contacts", {})
    return contacts.get("vk_call", ""), contacts.get("google_meet", "")


def _get_review_url(ui_payload: dict | None) -> str:
    info = build_teacher_info_from_ui(ui_payload)
    contacts = info.get("contacts", {})
    return contacts.get("review_url", "")


async def build_reschedule_slot_payloads(db: "Database") -> list[tuple[str, str]]:
    ui_payload = await _get_scheduler_ui_payload(db)
    info = build_teacher_info_from_ui(ui_payload)
    slots = await find_next_free_reschedule_slots(db, info=info)
    return [(encode_reschedule_slot(slot), format_reschedule_slot_label(slot)) for slot in slots]


def _build_payment_reminder_text(stage: str, speech_style: str | None = None, tone: str | None = None) -> str:
    prompt = choose_tone_variant(
        "Когда будет удобно, внесите",
        "Когда будет удобно, внесите",
        "Когда будет удобно, пожалуйста, внесите",
        "Когда будет удобно, пожалуйста, внесите",
        tone=tone,
    )
    evening_prompt = choose_tone_variant(
        "Постарайтесь",
        "Постарайтесь",
        "Пожалуйста, постарайтесь",
        "Буду признателен, если сможете",
        tone=tone,
    )
    if stage == "morning":
        return (
            "💰 <b>Напоминание об оплате</b>\n\n"
            "Доброе утро! Напоминаю, что занятия у нас оплачиваются на неделю вперёд.\n"
            f"Сейчас на {choose_form(speech_style, 'вашем', 'твоём')} балансе не осталось уроков.\n\n"
            f"{choose_form(speech_style, prompt, prompt.replace('внесите', 'внеси'))} оплату за ближайшую неделю.\n"
            "Реквизиты есть в меню: <b>💳 Реквизиты</b>."
        )

    return (
        "💰 <b>Оплата на новую неделю</b>\n\n"
        "Напоминаю, что для занятий на ближайшей неделе нужна предоплата.\n"
        "Сейчас уроков на балансе по-прежнему нет.\n\n"
        f"{choose_form(speech_style, evening_prompt, evening_prompt.replace('Постарайтесь', 'Постарайся').replace('сможете', 'сможешь'))} оплатить сегодня, чтобы расписание на неделю оставалось актуальным.\n"
        f"Если оплата уже отправлена или мы отдельно договорились, просто {choose_form(speech_style, 'проигнорируйте', 'проигнорируй')} это сообщение.\n\n"
        "Реквизиты: <b>💳 Реквизиты</b>."
    )


async def payment_reminder_job(bot, db: "Database", stage: str = "morning"):
    """Воскресные напоминания об оплате: мягкое утром и более серьёзное вечером."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        f"payment_reminder_{stage}",
        lambda _account: payment_reminder_job(bot, db, stage),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status(f"payment_reminder_{stage}", "ok", **aggregate)
            await write_runtime_event("payment_reminder", "ok", stage=stage, **aggregate)
        return

    target_hour = 11 if stage == "morning" else 22
    claimed, _local_now = await _claim_local_job_window(
        db,
        f"payment_reminder_{stage}",
        weekday=6,
        hour=target_hour,
        minute=0,
    )
    if not claimed:
        return {"skipped_accounts": 1}

    ui_payload = await _get_scheduler_ui_payload(db)
    tone = ui_tone(ui_payload)
    students = await db.get_students_with_balances()
    if not students:
        return {"unpaid": 0, "paid": 0}

    unpaid = []
    paid = []
    summary_title = (
        "📊 <b>Утренняя сводка по оплатам</b>\n"
        if stage == "morning" else
        "📊 <b>Вечерняя сводка по оплатам</b>\n"
    )

    for student in students:
        balance = student['lesson_balance']
        if balance == 0:
            unpaid.append((student['full_name'], balance))
            try:
                await bot.send_message(
                    student['telegram_id'],
                    _build_payment_reminder_text(stage, student.get("speech_style"), tone=tone),
                    reply_markup=make_teacher_reply_keyboard("payment"),
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание ученику {student['telegram_id']}: {e}")
        else:
            paid.append((student['full_name'], balance))

    # Сводка для преподавателя
    lines = [summary_title]
    if unpaid:
        lines.append(f"❌ <b>Не оплатили ({len(unpaid)}):</b>")
        for name, balance in unpaid:
            lines.append(f"  • {name} — {balance} ур.")
    if paid:
        lines.append(f"\n✅ <b>Оплатили ({len(paid)}):</b>")
        for name, balance in paid:
            lines.append(f"  • {name} — {balance} ур.")

    for chat_id in await _operator_recipient_ids(db):
        try:
            await bot.send_message(chat_id, "\n".join(lines))
        except Exception as e:
            logger.warning("Не удалось отправить account-scoped сводку по оплатам в %s: %s", chat_id, e)

    logger.info(
        "Напоминание об оплате (%s): %s не оплатили, %s оплатили.",
        stage,
        len(unpaid),
        len(paid),
    )
    if _should_emit_scheduler_metrics(db):
        await update_job_status(
            f"payment_reminder_{stage}",
            "ok",
            unpaid=len(unpaid),
            paid=len(paid),
        )
        await write_runtime_event("payment_reminder", "ok", stage=stage, unpaid=len(unpaid), paid=len(paid))
    return {"unpaid": len(unpaid), "paid": len(paid)}


async def homework_reminder_job(bot, db: "Database"):
    """Ежедневно в 20:00 — напоминание о ДЗ с дедлайном завтра."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "homework_reminder",
        lambda _account: homework_reminder_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("homework_reminder", "ok", **aggregate)
            await write_runtime_event("homework_reminder", "ok", **aggregate)
        return

    claimed, _local_now = await _claim_local_job_window(db, "homework_reminder", hour=20, minute=0)
    if not claimed:
        return {"skipped_accounts": 1}

    reference_now = await _account_reference_now(db)
    items = await _call_with_reference(db.get_homework_due_tomorrow, reference_now)
    for hw in items:
        try:
            deadline_str = hw['deadline'].strftime('%d.%m.%Y') if hw['deadline'] else '—'
            await bot.send_message(
                hw['telegram_id'],
                f"⏰ <b>Напоминание о домашнем задании!</b>\n\n"
                f"📝 {hw['title']}\n"
                f"📅 Срок сдачи: <b>завтра, {deadline_str}</b>\n\n"
                f"{choose_form(hw.get('speech_style'), 'Не забудьте', 'Не забудь')} про это задание.",
                reply_markup=make_teacher_reply_keyboard("homework", hw['id']),
            )
            await db.mark_homework_reminder_sent(hw['id'])
            logger.info(f"Напоминание ДЗ #{hw['id']} отправлено {hw['full_name']}")
        except Exception as e:
            logger.warning(f"Ошибка напоминания ДЗ #{hw['id']}: {e}")
    if _should_emit_scheduler_metrics(db):
        await update_job_status("homework_reminder", "ok", sent=len(items))
        await write_runtime_event("homework_reminder", "ok", sent=len(items))
    return {"sent": len(items)}


async def homework_gap_check_job(bot, db: "Database"):
    """Проверяет, задано ли новое ДЗ между предыдущим и ближайшим уроком."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "homework_gap_check",
        lambda _account: homework_gap_check_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("homework_gap_check", "ok", **aggregate)
            await write_runtime_event("homework_gap_check", "ok", **aggregate)
        return

    reference_now = await _account_reference_now(db)
    items = await _call_with_reference(db.get_lessons_missing_homework, reference_now)
    sent_count = 0
    recipients = await _operator_recipient_ids(db)

    if not recipients:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("homework_gap_check", "ok", sent=0, checked=len(items))
            await write_runtime_event("homework_gap_check", "ok", sent=0, checked=len(items))
        return {"sent": 0, "checked": len(items)}

    for lesson in items:
        previous_lesson = lesson.get("previous_lesson_date")
        previous_label = previous_lesson.strftime("%d.%m.%Y %H:%M") if previous_lesson else "—"
        next_label = lesson["lesson_date"].strftime("%d.%m.%Y %H:%M") if lesson.get("lesson_date") else "—"
        try:
            for chat_id in recipients:
                await bot.send_message(
                    chat_id,
                    "📚 <b>Проверьте домашнее задание</b>\n\n"
                    f"👤 Ученик: <b>{lesson['full_name']}</b>\n"
                    f"📅 Предыдущий урок: <b>{previous_label}</b>\n"
                    f"⏭ Ближайший урок: <b>{next_label}</b>\n\n"
                    "После предыдущего занятия пока не найдено новое ДЗ. Если оно уже выдано вне бота, это сообщение можно проигнорировать.",
                )
            await db.mark_homework_check_reminder_sent(lesson["id"])
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить напоминание по ДЗ для урока %s: %s", lesson["id"], exc)

    if _should_emit_scheduler_metrics(db):
        await update_job_status("homework_gap_check", "ok", sent=sent_count, checked=len(items))
        await write_runtime_event("homework_gap_check", "ok", sent=sent_count, checked=len(items))
    return {"sent": sent_count, "checked": len(items)}


async def lesson_reminder_job(bot, db: "Database"):
    """Напоминания о занятии: онлайн за ~10 минут, очно за ~1 час."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "lesson_reminder",
        lambda _account: lesson_reminder_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("lesson_reminder", "ok", **aggregate)
            await write_runtime_event("lesson_reminder", "ok", **aggregate)
        return

    from datetime import date
    reference_now = await _account_reference_now(db)
    lessons = await _call_with_reference(db.get_lessons_for_reminder, reference_now)
    current_local_date = reference_now.date()
    sent_count = 0
    ui_payload = await _get_scheduler_ui_payload(db)
    vk_call_url, google_meet_url = _get_online_lesson_links(ui_payload)
    for lesson in lessons:
        reminders = lesson.get('lesson_reminders') or 'enabled'
        # Проверяем паузу
        if reminders.startswith('paused_until:'):
            try:
                until_str = reminders.split(':', 1)[1]
                until_date = date.fromisoformat(
                    f"{until_str[6:10]}-{until_str[3:5]}-{until_str[0:2]}"
                )
                if current_local_date <= until_date:
                    continue
                else:
                    await db.set_lesson_reminders(lesson['telegram_id'], 'enabled')
            except Exception:
                continue

        try:
            lesson_time = lesson['lesson_date'].strftime('%H:%M')
            is_offline = (lesson.get('lesson_format') or 'online') == 'offline'
            lead_text = "через час" if is_offline else "через 10 минут"
            message_text = (
                f"⏰ <b>Напоминание о занятии!</b>\n\n"
                f"Урок начнётся <b>{lead_text}</b> (сегодня в <b>{lesson_time}</b>).\n"
            )
            if is_offline:
                message_text += (
                    "\n📍 Формат: <b>очный урок</b>.\n"
                    f"{choose_form(lesson.get('speech_style'), 'Пожалуйста, подтвердите, что будете вовремя.', 'Подтверди, что будешь вовремя.')}\n\n"
                )
            else:
                message_text += (
                    "\n📍 Формат: <b>онлайн</b>.\n"
                    + (f"📞 VK-Звонок: {vk_call_url}\n" if vk_call_url else "")
                    + (f"📹 Google Meet (для тех, кто активно использует VPN): {google_meet_url}\n" if google_meet_url else "")
                    + "\n"
                )
            message_text += "Чтобы отключить напоминания: Профиль → 🔔 Управление уведомлениями"
            await bot.send_message(
                lesson['telegram_id'],
                message_text,
                reply_markup=make_lesson_presence_keyboard(lesson['id']),
            )
            await db.mark_lesson_reminder_sent(lesson['id'])
            sent_count += 1
            logger.info(f"Напоминание об уроке отправлено {lesson['full_name']}")
        except Exception as e:
            logger.warning(f"Ошибка напоминания об уроке {lesson['id']}: {e}")
    if _should_emit_scheduler_metrics(db):
        await update_job_status("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))
        await write_runtime_event("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))
    return {"sent": sent_count, "checked": len(lessons)}


async def calendar_sync_job(bot, db: "Database"):
    """Каждые 30 минут — автосинхронизация Google Calendar."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "calendar_sync",
        lambda _account: calendar_sync_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("calendar_sync", "ok", **aggregate)
            await write_runtime_event("calendar_sync", "ok", **aggregate)
        return

    if not await db.has_capability("calendar_sync"):
        if _should_emit_scheduler_metrics(db):
            await update_job_status("calendar_sync", "ok", skipped="plan_locked")
            await write_runtime_event("calendar_sync", "ok", skipped="plan_locked")
        return {"skipped_accounts": 1}
    try:
        from utils.google_calendar import sync_calendar_to_db
        report = await sync_calendar_to_db(db)
        applied = report.get("imported", 0) + report.get("updated", 0)
        if applied or report.get("deleted", 0) or report.get("skipped", 0):
            logger.info(
                "Авто-синхронизация Google Calendar: imported=%s updated=%s skipped=%s deleted=%s.",
                report.get("imported", 0),
                report.get("updated", 0),
                report.get("skipped", 0),
                report.get("deleted", 0),
            )
        await update_ops_status(
            status="running",
            scheduler="running",
            last_calendar_sync=report.get("synced_at"),
            calendar_imported=report.get("imported", 0),
            calendar_updated=report.get("updated", 0),
            calendar_skipped=report.get("skipped", 0),
            calendar_deleted=report.get("deleted", 0),
        )
        if _should_emit_scheduler_metrics(db):
            await update_job_status(
                "calendar_sync",
                "ok",
                imported=report.get("imported", 0),
                updated=report.get("updated", 0),
                skipped=report.get("skipped", 0),
                deleted=report.get("deleted", 0),
            )
            await write_runtime_event(
                "calendar_sync",
                "ok",
                imported=report.get("imported", 0),
                updated=report.get("updated", 0),
                skipped=report.get("skipped", 0),
                deleted=report.get("deleted", 0),
            )
        return {
            "imported": int(report.get("imported", 0) or 0),
            "updated": int(report.get("updated", 0) or 0),
            "skipped": int(report.get("skipped", 0) or 0),
            "deleted": int(report.get("deleted", 0) or 0),
        }
    except Exception as e:
        logger.error(f"Ошибка авто-синхронизации Google Calendar: {e}")
        if _should_emit_scheduler_metrics(db):
            await update_job_status("calendar_sync", "error", error=str(e))
            await write_runtime_event("calendar_sync", "error", error=str(e))
        raise


async def lesson_completion_job(bot, db: "Database"):
    """Ежедневно в 00:30 локального времени аккаунта завершает прошедшие уроки."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "lesson_completion",
        lambda _account: lesson_completion_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("lesson_completion", "ok", **aggregate)
            await write_runtime_event("lesson_completion", "ok", **aggregate)
        return

    claimed, _local_now = await _claim_local_job_window(db, "lesson_completion", hour=0, minute=30)
    if not claimed:
        return {"skipped_accounts": 1}

    reference_now = await _account_reference_now(db)
    lessons = await _call_with_reference(db.get_past_unprocessed_lessons, reference_now)
    completed = 0
    consumed = 0
    awaiting_payment = 0
    for lesson in lessons:
        try:
            result = await db.complete_lesson(lesson['id'], lesson['student_id'])
            if result and result.get("completed"):
                completed += 1
            if result and result.get("consumed"):
                consumed += 1
            elif result and result.get("reason") == "awaiting_payment":
                awaiting_payment += 1
        except Exception as e:
            logger.warning(f"Ошибка завершения урока #{lesson['id']}: {e}")
    if completed:
        logger.info(
            "Авто-завершение: %s уроков завершено, списано %s, ждут оплаты %s.",
            completed,
            consumed,
            awaiting_payment,
        )
    if _should_emit_scheduler_metrics(db):
        await update_job_status(
            "lesson_completion",
            "ok",
            completed=completed,
            consumed=consumed,
            awaiting_payment=awaiting_payment,
        )
        await write_runtime_event(
            "lesson_completion",
            "ok",
            completed=completed,
            consumed=consumed,
            awaiting_payment=awaiting_payment,
        )
    return {
        "completed": completed,
        "consumed": consumed,
        "awaiting_payment": awaiting_payment,
    }


async def review_request_job(bot, db: "Database"):
    """Ежедневно в локальный полдень проверяет окно для запроса отзыва."""
    aggregate = await _run_scheduler_across_accounts(
        db,
        "review_request",
        lambda _account: review_request_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("review_request", "ok", **aggregate)
            await write_runtime_event("review_request", "ok", **aggregate)
        return

    ui_payload = await _get_scheduler_ui_payload(db)
    tone = ui_tone(ui_payload)
    claimed, _local_now = await _claim_local_job_window(db, "review_request", hour=12, minute=0)
    if not claimed:
        return {"skipped_accounts": 1}

    reference_now = await _account_reference_now(db)
    students = await _call_with_reference(db.get_students_for_review, reference_now)
    sent_count = 0
    review_url = _get_review_url(ui_payload)
    for student in students:
        try:
            review_link_block = f"👉 {review_url}\n\n" if review_url else ""
            await bot.send_message(
                student['telegram_id'],
                "⭐ <b>Оставьте отзыв о занятиях!</b>\n\n"
                "Прошло уже 3 недели с начала наших занятий.\n"
                f"Буду очень признателен, если {choose_form(student.get('speech_style'), 'Вы найдёте', 'ты найдёшь')} минутку и {choose_form(student.get('speech_style'), 'оставите', 'оставишь')} отзыв:\n\n"
                + review_link_block
                + choose_tone_variant(
                    "Это помогает другим ученикам быстрее сориентироваться.",
                    "Это очень помогает другим ученикам найти хорошего преподавателя.",
                    "Это очень помогает другим ученикам найти хорошего преподавателя 🙏",
                    "Это помогает другим ученикам принять решение о занятиях.",
                    tone=tone,
                ),
                reply_markup=make_teacher_reply_keyboard("review"),
            )
            await db.mark_review_sent(student['telegram_id'])
            sent_count += 1
            logger.info(f"Запрос отзыва отправлен: {student['full_name']} ({student['telegram_id']})")
        except Exception as e:
            logger.warning(f"Не удалось отправить запрос отзыва {student['telegram_id']}: {e}")
    if _should_emit_scheduler_metrics(db):
        await update_job_status("review_request", "ok", sent=sent_count, checked=len(students))
        await write_runtime_event("review_request", "ok", sent=sent_count, checked=len(students))
    return {"sent": sent_count, "checked": len(students)}


async def parent_weekly_digest_job(bot, db: "Database"):
    aggregate = await _run_scheduler_across_accounts(
        db,
        "parent_weekly_digest",
        lambda _account: parent_weekly_digest_job(bot, db),
    )
    if aggregate is not None:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("parent_weekly_digest", "ok", **aggregate)
            await write_runtime_event("parent_weekly_digest", "ok", **aggregate)
        return

    if not await db.has_capability("weekly_digest"):
        if _should_emit_scheduler_metrics(db):
            await update_job_status("parent_weekly_digest", "ok", skipped="plan_locked")
            await write_runtime_event("parent_weekly_digest", "ok", skipped="plan_locked")
        return {"skipped_accounts": 1}

    claimed, _local_now = await _claim_local_job_window(
        db,
        "parent_weekly_digest",
        weekday=6,
        hour=18,
        minute=0,
    )
    if not claimed:
        return {"skipped_accounts": 1}

    period_end = await _account_reference_now(db)
    period_start = period_end - timedelta(days=7)
    ui_payload = await _get_scheduler_ui_payload(db)
    rows = await db.get_parent_weekly_digest_rows(period_start, period_end)
    if not rows:
        if _should_emit_scheduler_metrics(db):
            await update_job_status("parent_weekly_digest", "ok", sent=0, checked=0)
            await write_runtime_event("parent_weekly_digest", "ok", sent=0, checked=0)
        return {"sent": 0, "checked": 0}

    grouped: dict[int, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row["parent_id"],
            {
                "parent_name": row["parent_name"],
                "items": [],
            },
        )
        bucket["items"].append(
            {
                "student_name": row["student_name"],
                "had_lesson": row["had_lesson"],
                "active_homework_count": row["active_homework_count"],
                "lesson_balance": row["lesson_balance"],
            }
        )

    sent_count = 0
    for parent_id, payload in grouped.items():
        try:
            await bot.send_message(
                parent_id,
                build_parent_weekly_digest_text(payload["parent_name"], payload["items"], tone=ui_tone(ui_payload)),
            )
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить weekly digest родителю %s: %s", parent_id, exc)

    if _should_emit_scheduler_metrics(db):
        await update_job_status("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))
        await write_runtime_event("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))
    return {"sent": sent_count, "checked": len(grouped)}


def setup_scheduler(bot, db: "Database") -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        lesson_completion_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db],
        id="lesson_completion",
        name="Авто-завершение прошедших уроков и списание баланса",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db, "morning"],
        id="payment_reminder_morning",
        name="Воскресное мягкое напоминание об оплате",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db, "evening"],
        id="payment_reminder_evening",
        name="Воскресное вечернее напоминание об оплате",
    )
    scheduler.add_job(
        review_request_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db],
        id="review_request",
        name="Запрос отзыва после 3 недель занятий",
    )
    scheduler.add_job(
        homework_reminder_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db],
        id="homework_reminder",
        name="Напоминание о ДЗ с дедлайном завтра",
    )
    scheduler.add_job(
        homework_gap_check_job,
        CronTrigger(minute=15),
        args=[bot, db],
        id="homework_gap_check",
        name="Проверка, задано ли ДЗ перед ближайшим уроком",
    )
    scheduler.add_job(
        lesson_reminder_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="lesson_reminder",
        name="Напоминание о занятии (онлайн 10м, очно 60м)",
    )
    scheduler.add_job(
        parent_weekly_digest_job,
        CronTrigger(minute="0,15,30,45"),
        args=[bot, db],
        id="parent_weekly_digest",
        name="Еженедельная сводка для родителей",
    )
    scheduler.add_job(
        calendar_sync_job,
        CronTrigger(minute="0,30"),
        args=[bot, db],
        id="calendar_auto_sync",
        name="Авто-синхронизация Google Calendar",
    )
    return scheduler
