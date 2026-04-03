import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from data import config
from data.config import load_teacher_info
from keyboards.inline import (
    make_lesson_presence_keyboard,
    make_teacher_reply_keyboard,
)
from utils.brand import choose_tone_variant
from utils.observability import update_job_status, update_ops_status, write_runtime_event
from utils.reschedule import encode_reschedule_slot, find_next_free_reschedule_slots, format_reschedule_slot_label
from utils.speech import choose_form
from utils.ui_text import build_parent_weekly_digest_text

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

logger = logging.getLogger(__name__)


def _get_online_lesson_links() -> tuple[str, str]:
    info = load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("vk_call", ""), contacts.get("google_meet", "")


def _get_review_url() -> str:
    info = load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("review_url", "")


async def build_reschedule_slot_payloads(db: "Database") -> list[tuple[str, str]]:
    slots = await find_next_free_reschedule_slots(db)
    return [(encode_reschedule_slot(slot), format_reschedule_slot_label(slot)) for slot in slots]


def _build_payment_reminder_text(stage: str, speech_style: str | None = None) -> str:
    prompt = choose_tone_variant(
        "Когда будет удобно, внесите",
        "Когда будет удобно, внесите",
        "Когда будет удобно, пожалуйста, внесите",
        "Когда будет удобно, пожалуйста, внесите",
    )
    evening_prompt = choose_tone_variant(
        "Постарайтесь",
        "Постарайтесь",
        "Пожалуйста, постарайтесь",
        "Буду признателен, если сможете",
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
    students = await db.get_students_with_balances()
    if not students:
        return

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
                    _build_payment_reminder_text(stage, student.get("speech_style")),
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

    if config.ADMIN_ID:
        try:
            await bot.send_message(config.ADMIN_ID, "\n".join(lines))
        except Exception as e:
            logger.warning(f"Не удалось отправить сводку администратору: {e}")

    logger.info(
        "Напоминание об оплате (%s): %s не оплатили, %s оплатили.",
        stage,
        len(unpaid),
        len(paid),
    )
    update_job_status(
        f"payment_reminder_{stage}",
        "ok",
        unpaid=len(unpaid),
        paid=len(paid),
    )
    write_runtime_event("payment_reminder", "ok", stage=stage, unpaid=len(unpaid), paid=len(paid))


async def homework_reminder_job(bot, db: "Database"):
    """Ежедневно в 20:00 — напоминание о ДЗ с дедлайном завтра."""
    items = await db.get_homework_due_tomorrow()
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
    update_job_status("homework_reminder", "ok", sent=len(items))
    write_runtime_event("homework_reminder", "ok", sent=len(items))


async def homework_gap_check_job(bot, db: "Database"):
    """Проверяет, задано ли новое ДЗ между предыдущим и ближайшим уроком."""
    items = await db.get_lessons_missing_homework()
    sent_count = 0

    if not config.ADMIN_ID:
        update_job_status("homework_gap_check", "ok", sent=0, checked=len(items))
        write_runtime_event("homework_gap_check", "ok", sent=0, checked=len(items))
        return

    for lesson in items:
        previous_lesson = lesson.get("previous_lesson_date")
        previous_label = previous_lesson.strftime("%d.%m.%Y %H:%M") if previous_lesson else "—"
        next_label = lesson["lesson_date"].strftime("%d.%m.%Y %H:%M") if lesson.get("lesson_date") else "—"
        try:
            await bot.send_message(
                config.ADMIN_ID,
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

    update_job_status("homework_gap_check", "ok", sent=sent_count, checked=len(items))
    write_runtime_event("homework_gap_check", "ok", sent=sent_count, checked=len(items))


async def lesson_reminder_job(bot, db: "Database"):
    """Напоминания о занятии: онлайн за ~10 минут, очно за ~1 час."""
    from datetime import date
    lessons = await db.get_lessons_for_reminder()
    sent_count = 0
    vk_call_url, google_meet_url = _get_online_lesson_links()
    for lesson in lessons:
        reminders = lesson.get('lesson_reminders') or 'enabled'
        # Проверяем паузу
        if reminders.startswith('paused_until:'):
            try:
                until_str = reminders.split(':', 1)[1]
                until_date = date.fromisoformat(
                    f"{until_str[6:10]}-{until_str[3:5]}-{until_str[0:2]}"
                )
                if date.today() <= until_date:
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
    update_job_status("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))
    write_runtime_event("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))


async def calendar_sync_job(bot, db: "Database"):
    """Каждые 30 минут — автосинхронизация Google Calendar."""
    if not await db.has_capability("calendar_sync"):
        update_job_status("calendar_sync", "ok", skipped="plan_locked")
        write_runtime_event("calendar_sync", "ok", skipped="plan_locked")
        return
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
        update_ops_status(
            status="running",
            scheduler="running",
            last_calendar_sync=report.get("synced_at"),
            calendar_imported=report.get("imported", 0),
            calendar_updated=report.get("updated", 0),
            calendar_skipped=report.get("skipped", 0),
            calendar_deleted=report.get("deleted", 0),
        )
        update_job_status(
            "calendar_sync",
            "ok",
            imported=report.get("imported", 0),
            updated=report.get("updated", 0),
            skipped=report.get("skipped", 0),
            deleted=report.get("deleted", 0),
        )
        write_runtime_event(
            "calendar_sync",
            "ok",
            imported=report.get("imported", 0),
            updated=report.get("updated", 0),
            skipped=report.get("skipped", 0),
            deleted=report.get("deleted", 0),
        )
    except Exception as e:
        logger.error(f"Ошибка авто-синхронизации Google Calendar: {e}")
        update_job_status("calendar_sync", "error", error=str(e))
        write_runtime_event("calendar_sync", "error", error=str(e))


async def lesson_completion_job(bot, db: "Database"):
    """Ежедневно в 00:30 МСК — завершает прошедшие уроки и списывает баланс."""
    lessons = await db.get_past_unprocessed_lessons()
    count = 0
    for lesson in lessons:
        try:
            await db.complete_lesson(lesson['id'], lesson['student_id'])
            count += 1
        except Exception as e:
            logger.warning(f"Ошибка завершения урока #{lesson['id']}: {e}")
    if count:
        logger.info(f"Авто-завершение: {count} уроков завершено, баланс списан.")
    update_job_status("lesson_completion", "ok", completed=count)
    write_runtime_event("lesson_completion", "ok", completed=count)


async def review_request_job(bot, db: "Database"):
    """Ежедневно проверяет, прошло ли 3 недели с первого занятия — отправляет просьбу об отзыве."""
    students = await db.get_students_for_review()
    sent_count = 0
    review_url = _get_review_url()
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
                ),
                reply_markup=make_teacher_reply_keyboard("review"),
            )
            await db.mark_review_sent(student['telegram_id'])
            sent_count += 1
            logger.info(f"Запрос отзыва отправлен: {student['full_name']} ({student['telegram_id']})")
        except Exception as e:
            logger.warning(f"Не удалось отправить запрос отзыва {student['telegram_id']}: {e}")
    update_job_status("review_request", "ok", sent=sent_count, checked=len(students))
    write_runtime_event("review_request", "ok", sent=sent_count, checked=len(students))


async def parent_weekly_digest_job(bot, db: "Database"):
    if not await db.has_capability("weekly_digest"):
        update_job_status("parent_weekly_digest", "ok", skipped="plan_locked")
        write_runtime_event("parent_weekly_digest", "ok", skipped="plan_locked")
        return
    period_end = datetime.now()
    period_start = period_end - timedelta(days=7)
    rows = await db.get_parent_weekly_digest_rows(period_start, period_end)
    if not rows:
        update_job_status("parent_weekly_digest", "ok", sent=0, checked=0)
        write_runtime_event("parent_weekly_digest", "ok", sent=0, checked=0)
        return

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
                build_parent_weekly_digest_text(payload["parent_name"], payload["items"]),
            )
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить weekly digest родителю %s: %s", parent_id, exc)

    update_job_status("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))
    write_runtime_event("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))


def setup_scheduler(bot, db: "Database") -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        lesson_completion_job,
        CronTrigger(hour=0, minute=30),
        args=[bot, db],
        id="lesson_completion",
        name="Авто-завершение прошедших уроков и списание баланса",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(day_of_week="sun", hour=11, minute=0),
        args=[bot, db, "morning"],
        id="payment_reminder_morning",
        name="Воскресное мягкое напоминание об оплате",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(day_of_week="sun", hour=22, minute=0),
        args=[bot, db, "evening"],
        id="payment_reminder_evening",
        name="Воскресное вечернее напоминание об оплате",
    )
    scheduler.add_job(
        review_request_job,
        CronTrigger(hour=12, minute=0),
        args=[bot, db],
        id="review_request",
        name="Запрос отзыва после 3 недель занятий",
    )
    scheduler.add_job(
        homework_reminder_job,
        CronTrigger(hour=20, minute=0),
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
        CronTrigger(day_of_week="sun", hour=18, minute=0),
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
