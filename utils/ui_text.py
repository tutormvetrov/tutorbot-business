from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from aiogram import html

from data.config import get_product_name
from utils.brand import (
    DEFAULT_BRAND_TONE,
    brand_tone_description,
    brand_tone_label,
    choose_tone_variant,
)
from utils.speech import speech_style_label
from utils.workspace import workspace_role_label

MAIN_MENU_TEXT = "Главное меню:"
ACTION_CANCELLED_TEXT = "❌ Действие отменено."
REGISTRATION_REQUIRED_TEXT = "⚠️ Сначала зарегистрируйтесь через /start"
DEACTIVATED_ACCOUNT_TEXT = "⛔️ Ваш аккаунт деактивирован. Обратитесь к преподавателю."

ADMIN_HOME_TEXT = (
    "🛠 <b>Панель администратора</b>\n\n"
    "Сверху — живая сводка по боту. Ниже — рабочие разделы по задачам."
)
ADMIN_STUDENTS_CATEGORY_TEXT = (
    "👥 <b>Ученики</b>\n\n"
    "Сначала откройте список учеников или добавьте нового.\n"
    "Здесь же находятся формат занятий, обращение и действия по доступу."
)
ADMIN_EDUCATION_CATEGORY_TEXT = (
    "📚 <b>Учебный процесс</b>\n\n"
    "Здесь собраны все учебные действия: занятия, оплаты, домашние задания и заморозки."
)
ADMIN_COMMUNICATION_CATEGORY_TEXT = (
    "📢 <b>Коммуникации</b>\n\n"
    "Рассылки, ответы ученикам и служебные сообщения."
)
ADMIN_ACCOUNT_CATEGORY_TEXT = (
    "🏢 <b>Аккаунт и рост</b>\n\n"
    "Быстрый запуск, тариф, команда, аналитика и всё, что помогает держать аккаунт в рабочем состоянии."
)
ADMIN_SERVICE_CATEGORY_TEXT = (
    "⚙️ <b>Сервис</b>\n\n"
    "Раздел стал короче: отсюда можно перейти к настройке аккаунта или к системным инструментам."
)
ADMIN_SYSTEM_CATEGORY_TEXT = (
    "🖥 <b>Система и диагностика</b>\n\n"
    "Интеграции, Calendar, здоровье бота, заметки и служебная диагностика."
)
ADMIN_SYNC_IN_PROGRESS_TEXT = "🔄 Синхронизирую Google Calendar..."
ADMIN_SYNC_ERROR_HINT = (
    "Проверьте путь в <b>GOOGLE_CREDENTIALS_FILE</b> "
    "и корректность <b>GOOGLE_CALENDAR_ID</b>."
)

ADMIN_NO_REGISTERED_STUDENTS_TEXT = (
    "⚠️ <b>Пока нет учеников</b>\n\n"
    "Сначала добавьте первого ученика, а затем вернитесь к занятиям."
)
ADMIN_NO_ACTIVE_STUDENTS_TEXT = "👥 Нет активных учеников."
ADMIN_STUDENTS_EMPTY_TEXT = (
    "👥 <b>Список учеников</b>\n\n"
    "Пока здесь пусто. Добавьте первого ученика из панели или попросите его сначала открыть бота через <code>/start</code>."
)
ADMIN_LESSON_FORMATS_EMPTY_TEXT = "🏫 <b>Формат занятий</b>\n\nСейчас нет активных учеников, для которых можно переключить формат."
ADMIN_SPEECH_STYLES_EMPTY_TEXT = "🗣 <b>Обращение с учениками</b>\n\nСейчас нет активных учеников, для которых можно переключить обращение."
ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT = (
    "📢 <b>Рассылка пока недоступна</b>\n\n"
    "Сейчас нет активных учеников, которым можно отправить сообщение."
)

ADMIN_ADD_LESSON_START_TEXT = (
    "➕ <b>Добавить занятие</b>\n\n"
    "Выберите ученика, для которого хотите поставить первое или следующее занятие."
)
ADMIN_ADD_LESSON_PROMPT_TEXT = (
    "📅 Введите дату и время занятия в формате:\n"
    "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
    "Например: <code>15.06.2025 14:00</code>"
)
ADMIN_ADD_LESSON_INVALID_TEXT = (
    "⚠️ Пока не получилось распознать дату. Введите её так:\n<code>15.06.2025 14:00</code>"
)
ADMIN_ADD_PAYMENT_START_TEXT = "💳 <b>Добавить оплату</b>\n\nВыберите ученика, чтобы зафиксировать оплату."
ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT = (
    "💰 Введите сумму оплаты в рублях.\n\nНапример: <code>3000</code>"
)
ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT = (
    "⚠️ Нужна корректная сумма. Например: <code>3000</code>"
)
ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT = (
    "🔢 Сколько уроков оплачено?\n\nНапример: <code>1</code>"
)
ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT = (
    "⚠️ Нужна целая положительная цифра. Например: <code>1</code>"
)
ADMIN_ADD_HOMEWORK_START_TEXT = "📚 <b>Задать домашнее задание</b>\n\nВыберите ученика."
ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT = "📝 Введите <b>текст домашнего задания</b>. Можно со ссылками и форматированием."
ADMIN_ADD_HOMEWORK_EMPTY_TEXT = "⚠️ Текст задания не может быть пустым."
ADMIN_ADD_HOMEWORK_DEADLINE_PROMPT_TEXT = (
    "📅 Введите дедлайн в формате <code>ДД.ММ.ГГГГ</code>.\n\n"
    "Подойдут варианты: <code>05.04.2026</code>, <code>05/04/2026</code> или <code>05\\04\\2026</code>"
)
ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT = (
    "⚠️ Не удалось распознать дату. Введите её так: "
    "<code>05.04.2026</code>, <code>05/04/2026</code> или <code>05\\04\\2026</code>"
)
ADMIN_BROADCAST_START_TEXT = (
    "📢 <b>Рассылка ученикам</b>\n\n"
    "Можно выбрать готовый шаблон или отправить своё сообщение.\n"
    "Перед отправкой бот покажет точный предпросмотр."
)
ADMIN_BROADCAST_ENTER_TEXT = (
    "✏️ Введите текст сообщения для рассылки.\n\n"
    "Можно использовать форматирование и ссылки. Перед отправкой вы ещё увидите предпросмотр."
)
ADMIN_BROADCAST_EDIT_TEXT = (
    "✏️ Введите обновлённый текст сообщения.\n\n"
    "После этого снова покажу предпросмотр."
)
ADMIN_HEALTH_NO_ERRORS_TEXT = "✅ В последних runtime-логах ошибок не найдено."

LESSON_FORMAT_LABELS = {
    "online": "онлайн",
    "offline": "очно",
}
LESSON_FORMAT_ICONS = {
    "online": "💻",
    "offline": "🏠",
}


def format_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return value.strftime("%d.%m.%Y")


def format_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def format_short_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m %H:%M") if value else "—"


def _add_calendar_month(value: date) -> date:
    month = value.month + 1
    year = value.year
    if month > 12:
        month = 1
        year += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def student_freshness_label(first_lesson_date: datetime | None, today: date | None = None) -> str:
    if not first_lesson_date:
        return "новый"
    today = today or date.today()
    rollover_date = _add_calendar_month(first_lesson_date.date())
    return "старый" if today >= rollover_date else "новый"


def student_freshness_badge(first_lesson_date: datetime | None, today: date | None = None) -> str:
    label = student_freshness_label(first_lesson_date, today=today)
    return "🆕 новый" if label == "новый" else "📘 старый"


def lesson_balance_label(balance: int | None) -> str:
    amount = int(balance or 0)
    return f"{amount} уроков" if amount else "0 уроков"


def lesson_format_label(value: str | None) -> str:
    return LESSON_FORMAT_LABELS.get(value or "online", LESSON_FORMAT_LABELS["online"])


def lesson_format_icon(value: str | None) -> str:
    return LESSON_FORMAT_ICONS.get(value or "online", LESSON_FORMAT_ICONS["online"])


def reminder_status_label(reminders: str | None) -> str:
    reminders = reminders or "enabled"
    if reminders == "disabled":
        return "отключены"
    if reminders.startswith("paused_until:"):
        return f"на паузе до {reminders.split(':', 1)[1]}"
    return "включены"


def reminder_status_hint(reminders: str | None) -> str:
    reminders = reminders or "enabled"
    if reminders == "disabled":
        return "Сейчас напоминания не приходят. Их можно включить в один клик."
    if reminders.startswith("paused_until:"):
        until = reminders.split(":", 1)[1]
        return f"Пауза действует до <b>{html.quote(until)}</b>. После этого напоминания снова включатся автоматически."
    return (
        "Онлайн-уроки: напоминание за <b>10 минут</b>.\n"
        "Очные уроки: напоминание за <b>1 час</b>."
    )


def next_lesson_label(lessons: list) -> str:
    lesson_date = None
    for lesson in lessons or []:
        if lesson.get("lesson_date"):
            lesson_date = lesson["lesson_date"]
            break
    if not lesson_date:
        return "не назначено"
    return format_datetime(lesson_date)


def build_schedule_text(lessons: list) -> str:
    if not lessons:
        return (
            "📅 <b>Расписание</b>\n\n"
            "Расписание пока пустое.\n\n"
            "Как только преподаватель поставит первое занятие, оно сразу появится здесь."
        )

    next_lesson = None
    lines = []
    for lesson in lessons:
        lesson_date = lesson.get("lesson_date")
        if lesson_date and next_lesson is None:
            next_lesson = lesson_date
        lines.append(f"• <b>{format_datetime(lesson_date)}</b>")

    title = "📅 <b>Расписание</b>"
    if next_lesson:
        title += f"\n\nБлижайший урок: <b>{format_datetime(next_lesson)}</b>"
    title += f"\nВсего в расписании: <b>{len(lessons)}</b>"
    return title + "\n\n" + "\n".join(lines)


def build_profile_text(
    user,
    balance: int,
    lessons: list | None = None,
    reminders: str | None = None,
    children: list[str] | None = None,
    next_lesson: datetime | None = None,
) -> str:
    role_labels = {
        "student": workspace_role_label("student"),
        "parent": workspace_role_label("parent"),
        "owner": workspace_role_label("owner"),
        "manager": workspace_role_label("manager"),
        "assistant": workspace_role_label("assistant"),
    }
    reg_date = format_date(user.get("registration_date"))
    full_name = html.quote(user.get("full_name") or "—")
    role_label = role_labels.get(user.get("role"), user.get("role") or "—")

    lines = [
        "👤 <b>Ваш профиль</b>",
        "",
        f"Здравствуйте, <b>{full_name}</b>.",
        f"🎭 Роль: <b>{role_label}</b>",
        f"📅 В системе с: <b>{reg_date}</b>",
    ]

    if user.get("role") == "student":
        lesson_label = format_datetime(next_lesson) if next_lesson else next_lesson_label(lessons or [])
        lines.extend([
            f"🎓 Остаток уроков: <b>{lesson_balance_label(balance)}</b>",
            f"📅 Ближайшее занятие: <b>{html.quote(lesson_label)}</b>",
            f"🔔 Напоминания: <b>{html.quote(reminder_status_label(reminders))}</b>",
            f"🏫 Формат занятий: <b>{lesson_format_label(user.get('lesson_format'))}</b>",
        ])
    elif user.get("role") == "parent":
        lines.append("👨‍👩‍👧 <b>Дети в системе:</b>")
        if children:
            for child in children:
                lines.append(f"• {html.quote(child)}")
        else:
            lines.append("• Пока ни один ученик не привязан. Если связь уже должна быть, напишите преподавателю.")

    lines.append("")
    lines.append("Если что-то нужно поменять или уточнить, нужное действие уже есть в кнопках ниже.")
    return "\n".join(lines)


def build_parent_children_text(children: list[str] | None) -> str:
    lines = [
        "👨‍👩‍👧 <b>Дети в аккаунте</b>",
        "",
    ]
    if not children:
        lines.extend([
            "Пока ни один ученик не привязан.",
            "Если связь уже должна быть, напишите преподавателю через контакты.",
        ])
        return "\n".join(lines)

    lines.append(f"Сейчас привязано детей: <b>{len(children)}</b>")
    lines.append("")
    for child in children:
        lines.append(f"• {html.quote(child)}")
    lines.extend([
        "",
        "Еженедельная сводка по занятиям приходит автоматически. Если список нужно обновить, свяжитесь с преподавателем.",
    ])
    return "\n".join(lines)


def build_payment_text(balance: int, payments: list) -> str:
    lines = [
        "💰 <b>Оплата</b>",
        "",
        f"Сейчас на балансе: <b>{lesson_balance_label(balance)}</b>",
    ]

    if not payments:
        lines.extend([
            "",
            "Пока ни одной оплаты не внесено.",
            "После первой оплаты здесь появится история и остаток уроков по каждой записи.",
        ])
        return "\n".join(lines)

    lines.extend([
        "",
        "Последние оплаты:",
    ])
    for index, payment in enumerate(payments, 1):
        date_str = format_date(payment.get("payment_date"))
        lines.append(
            f"• {index}. <b>{int(payment['amount'])} ₽</b> · {payment['lessons_count']} ур. · "
            f"{lesson_balance_label(payment.get('lessons_remaining'))} · {date_str}"
        )
    return "\n".join(lines)


def build_contacts_text(
    info: dict,
    show_address: bool = False,
    *,
    tone: str | None = None,
    intro_text: str | None = None,
) -> str:
    contacts = info.get("contacts", {})
    tone = tone or DEFAULT_BRAND_TONE
    lines = [
        "📞 <b>Контакты преподавателя</b>",
        "",
        intro_text
        or choose_tone_variant(
            "Здесь собраны основные способы связи и подключения к занятию.",
            "Здесь собраны быстрые способы связи и подключения к занятию.",
            "Здесь собраны быстрые способы связи и подключения к занятию.",
            "Здесь собраны удобные способы связи и подключения к занятию.",
            tone=tone,
        ),
    ]
    if contacts.get("project_site_url"):
        lines.extend([
            "",
            "🌐 <b>Сайт и материалы</b>",
            "Там есть тест уровня, информация о занятиях и полезные материалы.",
        ])
    if contacts.get("phone"):
        lines.append(f"📱 Телефон: <b>{html.quote(contacts['phone'])}</b>")
    if contacts.get("telegram"):
        lines.append(f"💬 Telegram: <b>{html.quote(contacts['telegram'])}</b>")
    if contacts.get("discord"):
        lines.append(f"🎮 Discord: <b>{html.quote(contacts['discord'])}</b>")

    if contacts.get("vk_call") or contacts.get("google_meet"):
        lines.extend([
            "",
            "💻 <b>Онлайн-занятия</b>",
            "Кнопки ниже откроют нужный сервис в один тап.",
            "VK Звонок — основной вариант, Google Meet — запасной, если нужен VPN.",
        ])

    if show_address and contacts.get("address"):
        lines.extend([
            "",
            "🏠 <b>Очные занятия</b>",
            html.quote(contacts["address"]),
        ])
    elif contacts.get("address"):
        lines.extend([
            "",
            "🏠 <b>Очные занятия</b>",
            "Адрес доступен зарегистрированным ученикам и родителям.",
        ])

    return "\n".join(lines)


def build_help_text(
    *,
    tone: str | None = None,
    product_name: str | None = None,
    intro_text: str | None = None,
) -> str:
    tone = tone or DEFAULT_BRAND_TONE
    product_name = product_name or get_product_name()
    site_line = choose_tone_variant(
        "↗️ <b>Сайт и материалы</b> — тест уровня и основные материалы преподавателя",
        "↗️ <b>Сайт и материалы</b> — тест уровня, информация о занятиях и полезные материалы",
        "↗️ <b>Сайт и материалы</b> — тест уровня, информация о занятиях и полезные материалы",
        "↗️ <b>Сайт и материалы</b> — тест уровня и материалы по занятиям",
        tone=tone,
    )
    intro_block = f"{html.quote(intro_text)}\n\n" if intro_text else ""
    return (
        f"🤖 <b>Справка по {html.quote(product_name)}</b>\n\n"
        f"{intro_block}"
        "<b>Команды</b>\n"
        "/start — начать работу / войти\n"
        "/menu — главное меню\n"
        "/profile — мой профиль\n"
        "/help — эта справка\n\n"
        "<b>Основные разделы</b>\n"
        "📅 Расписание\n"
        "📚 Домашние задания\n"
        "💰 Оплата\n"
        "👤 Профиль и уведомления\n"
        "📞 Контакты и ссылки\n"
        "💳 Реквизиты\n"
        "💼 Продукт и тариф\n"
        f"{site_line}"
    )


def build_brand_tone_text(current_tone: str | None) -> str:
    current_label = brand_tone_label(current_tone)
    current_description = brand_tone_description(current_tone)
    return (
        "🎨 <b>Тональность бренда</b>\n\n"
        f"Сейчас бот говорит в режиме: <b>{html.quote(current_label)}</b>.\n"
        f"{html.quote(current_description)}\n\n"
        "Ниже можно переключить общий стиль формулировок для автоматических сообщений, шаблонных рассылок и ключевых экранов."
    )


def build_parent_weekly_digest_text(parent_name: str, items: list[dict], *, tone: str | None = None) -> str:
    tone = tone or DEFAULT_BRAND_TONE
    intro = choose_tone_variant(
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        tone=tone,
    )
    lines = [
        "👨‍👩‍👧 <b>Еженедельная сводка</b>",
        "",
        f"{html.quote(parent_name)}, {intro}",
    ]
    for item in items:
        lines.extend([
            "",
            f"• <b>{html.quote(item['student_name'])}</b>",
            f"  📅 Урок за неделю: <b>{'был' if item['had_lesson'] else 'не было'}</b>",
            f"  📚 Активные ДЗ: <b>{item['active_homework_count']}</b>",
            f"  🎓 Баланс уроков: <b>{lesson_balance_label(item['lesson_balance'])}</b>",
        ])
    return "\n".join(lines)


def build_requisites_text(req: dict, *, footer_text: str | None = None) -> str:
    lines = [
        "💳 <b>Реквизиты и стоимость</b>",
        "",
    ]
    rates = req.get("rates") or ([req["rate"]] if req.get("rate") else [])
    if rates:
        lines.append("📌 <b>Стоимость занятия</b>")
        for item in rates:
            lines.append(html.quote(item))
    if req.get("card"):
        lines.extend([
            "",
            "💳 <b>Карта</b>",
            f"<code>{html.quote(req['card'])}</code>",
        ])
    if req.get("sbp"):
        banks = f" ({html.quote(req['sbp_banks'])})" if req.get("sbp_banks") else ""
        lines.extend([
            "",
            f"📱 <b>СБП</b>{banks}",
            f"<code>{html.quote(req['sbp'])}</code>",
        ])
    if req.get("usdt_trc20"):
        lines.extend([
            "",
            "🪙 <b>USDT TRC-20</b>",
            f"<code>{html.quote(req['usdt_trc20'])}</code>",
        ])
    lines.extend([
        "",
        footer_text or "Если уже отправили оплату, можно сразу нажать кнопку <b>«Сообщить об оплате»</b> ниже в разделе оплаты.",
    ])
    return "\n".join(lines)


def build_notifications_text(reminders: str | None) -> str:
    return (
        "🔔 <b>Напоминания о занятиях</b>\n\n"
        f"Текущий статус: <b>{html.quote(reminder_status_label(reminders))}</b>\n\n"
        f"{reminder_status_hint(reminders)}"
    )


def _group_active_homework(items: list, today: date) -> list[tuple[str, list]]:
    urgent = []
    upcoming = []
    later = []
    no_deadline = []
    for item in items:
        deadline = item.get("deadline")
        if not deadline:
            no_deadline.append(item)
            continue
        item_date = deadline.date() if isinstance(deadline, datetime) else deadline
        if item_date <= today:
            urgent.append(item)
        elif item_date <= today + timedelta(days=3):
            upcoming.append(item)
        else:
            later.append(item)
    groups = []
    if urgent:
        groups.append(("⏰ <b>Срочно</b>", urgent))
    if upcoming:
        groups.append(("📌 <b>Ближайшее</b>", upcoming))
    if later:
        groups.append(("🗂 <b>Дальше</b>", later))
    if no_deadline:
        groups.append(("📚 <b>Без указанного дедлайна</b>", no_deadline))
    return groups


def build_homework_list_text(items: list, status: str, today: date | None = None) -> str:
    today = today or date.today()
    if status == "done":
        lines = [f"✅ <b>Выполненные задания</b> ({len(items)})"]
        for index, hw in enumerate(items, 1):
            lines.extend(["", f"✅ <b>{index}. {hw['title']}</b> · {format_date(hw.get('deadline'))}"])
            if hw.get("description"):
                lines.append(f"📄 {hw['description']}")
        return "\n".join(lines)

    lines = [f"📚 <b>Активные задания</b> ({len(items)})"]
    groups = _group_active_homework(items, today)
    if not groups:
        groups = [("📚 <b>Задания</b>", items)]

    counter = 1
    for group_title, group_items in groups:
        lines.extend(["", group_title])
        for hw in group_items:
            lines.extend(["", f"📝 <b>{counter}. {hw['title']}</b> · {format_date(hw.get('deadline'))}"])
            if hw.get("description"):
                lines.append(f"📄 {hw['description']}")
            counter += 1
    return "\n".join(lines)


def build_homework_empty_text(status: str) -> str:
    if status == "done":
        return (
            "✅ <b>Выполненные задания</b>\n\n"
            "Пока здесь ничего нет. Как только вы отметите задание как выполненное, оно появится в этом разделе."
        )
    return (
        "📚 <b>Активные задания</b>\n\n"
        "Сейчас активных домашних заданий нет. Когда преподаватель добавит новое, оно сразу появится здесь."
    )


def build_homework_text(items: list, status: str) -> str:
    if not items:
        return build_homework_empty_text(status)
    return build_homework_list_text(items, status)


def build_action_result_text(title: str, body: str, next_step: str = "", icon: str = "✅") -> str:
    lines = [f"{icon} <b>{title}</b>", "", body]
    if next_step:
        lines.extend(["", next_step])
    return "\n".join(lines)


def build_reply_sent_text(*, tone: str | None = None) -> str:
    follow_up = choose_tone_variant(
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель увидит его в ближайшее время.",
        tone=tone or DEFAULT_BRAND_TONE,
    )
    return (
        "✅ <b>Сообщение отправлено</b>\n\n"
        f"{follow_up} Если понадобится, можете написать ещё раз из нужного раздела."
    )


def build_homework_done_text(title: str) -> str:
    return (
        "✅ <b>Отлично, отмечено как выполненное</b>\n\n"
        f"Задание «{title}» перенесено в выполненные."
    )


def build_freeze_intro_text(active_count: int) -> str:
    return (
        "❄️ <b>Заморозка занятий</b>\n\n"
        f"Сейчас можно отправить заявку на заморозку для <b>{active_count}</b> активных занятий.\n\n"
        "Выберите причину ниже, а затем мы ещё раз коротко всё подтвердим перед отправкой."
    )


def build_freeze_confirm_text(reason_label: str, active_count: int) -> str:
    lesson_word = "занятия" if active_count % 10 in {2, 3, 4} and active_count % 100 not in {12, 13, 14} else "занятий"
    return (
        "❄️ <b>Подтверждение заморозки</b>\n\n"
        f"Причина: <b>{html.quote(reason_label)}</b>\n"
        f"Будет затронуто: <b>{active_count}</b> {lesson_word}\n\n"
        "После отправки преподаватель увидит заявку и подтвердит её или свяжется с вами для уточнения.\n\n"
        "Если всё верно, отправьте заявку."
    )


def build_freeze_success_text(
    reason_label: str | None = None,
    affected_count: int | None = None,
    *,
    tone: str | None = None,
) -> str:
    details = []
    if reason_label:
        details.append(f"Причина: <b>{html.quote(reason_label)}</b>")
    if affected_count is not None:
        details.append(f"Затронуто занятий: <b>{affected_count}</b>")
    details_block = ("\n" + "\n".join(details) + "\n") if details else "\n"
    return (
        "✅ <b>Заявка на заморозку отправлена</b>\n"
        f"{details_block}\n"
        f"{choose_tone_variant('Преподаватель ответит позже.', 'Преподаватель увидит её и ответит вам, как только сможет.', 'Преподаватель увидит её и ответит вам, как только сможет.', 'Преподаватель увидит заявку и вернётся с ответом, как только сможет.', tone=tone or DEFAULT_BRAND_TONE)}\n"
        "Пока ничего дополнительно делать не нужно."
    )


def build_self_delete_warning_text(user, snapshot: dict) -> str:
    role = user.get("role")
    full_name = html.quote(user.get("full_name") or "этот профиль")

    if role == "student":
        lines = [
            f"🗑 <b>Удалить профиль {full_name}?</b>",
            "",
            "Перед удалением важно проверить, что вы действительно хотите очистить все данные внутри бота.",
            "",
            f"📅 Занятий: <b>{snapshot.get('lessons', 0)}</b>",
            f"💳 Оплат: <b>{snapshot.get('payments_as_student', 0)}</b>",
            f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>",
        ]
        if snapshot.get("calendar_links"):
            lines.append(f"🧭 Календарных связей: <b>{snapshot.get('calendar_links', 0)}</b>")
        if snapshot.get("parent_links_as_student"):
            lines.append(f"👨‍👩‍👧 Родительских связей: <b>{snapshot.get('parent_links_as_student', 0)}</b>")
        lines.extend([
            "",
            "После удаления профиль, занятия, оплаты и домашние задания исчезнут из базы.",
            "Если позже вы снова зайдёте в бота и отправите <code>/start</code>, регистрацию можно будет пройти заново.",
            "",
            "⚠️ Это действие необратимо.",
        ])
        return "\n".join(lines)

    if role == "parent":
        lines = [
            f"🗑 <b>Удалить родительский профиль {full_name}?</b>",
            "",
            "Мы удалим только родительский профиль и связи внутри бота.",
            "",
            f"👨‍👩‍👧 Связей с учениками: <b>{snapshot.get('parent_links_as_parent', 0)}</b>",
        ]
        if snapshot.get("payments_as_payer"):
            lines.append(f"💳 Оплат как плательщика: <b>{snapshot.get('payments_as_payer', 0)}</b>")
        lines.extend([
            "",
            "Профили учеников при этом не удаляются.",
            "Если понадобится, вы сможете снова зарегистрироваться как родитель через <code>/start</code>.",
            "",
            "⚠️ Это действие необратимо.",
        ])
        return "\n".join(lines)

    return (
        "🗑 <b>Удалить профиль?</b>\n\n"
        "Это действие необратимо. Если хотите продолжить, подтвердите удаление."
    )


def build_self_delete_success_text(role: str | None) -> str:
    if role == "parent":
        return (
            "✅ <b>Родительский профиль удалён</b>\n\n"
            "Связи внутри бота очищены. При необходимости вы сможете зарегистрироваться снова через <code>/start</code>."
        )
    return (
        "✅ <b>Профиль удалён</b>\n\n"
        "Данные очищены из базы бота. Если позже захотите вернуться, просто отправьте <code>/start</code> и пройдите регистрацию заново."
    )


def build_level_test_text(action: str, has_url: bool, *, tone: str | None = None) -> str:
    if action == "now" and has_url:
        return (
            "🧪 <b>Тест уровня</b>\n\n"
            + choose_tone_variant(
                "Кнопка ниже сразу откроет тест.",
                "Кнопка ниже сразу откроет тест, чтобы можно было пройти его в удобный момент.",
                "Отлично. Кнопка ниже сразу откроет тест, чтобы можно было пройти его в удобный момент.",
                "Кнопка ниже сразу откроет тест в удобный для вас момент.",
                tone=tone or DEFAULT_BRAND_TONE,
            )
        )
    if action == "now":
        return (
            "🧪 <b>Тест уровня</b>\n\n"
            "Ссылка на тест пока не добавлена. Напишите преподавателю, и он пришлёт её отдельно."
        )
    if action == "later":
        return (
            "🕒 <b>Хорошо</b>\n\n"
            "Тест можно пройти позже. Кнопка <b>«🧪 Тест уровня»</b> останется в профиле."
        )
    return (
        "🙏 <b>Понял</b>\n\n"
        "Если позже захотите пройти тест, он всё равно будет доступен в профиле."
    )


def build_broadcast_preview_text(broadcast_text: str) -> str:
    return (
        "📢 <b>Предпросмотр рассылки</b>\n\n"
        "Именно так сообщение увидят выбранные ученики:\n\n"
        f"{broadcast_text}\n\n"
        "Если всё выглядит хорошо, можно перейти к выбору получателей."
    )


def admin_broadcast_recipients_text(preview: str, selected_count: int, total_count: int) -> str:
    clean_preview = re.sub(r"<[^>]+>", "", preview or "").strip()
    if len(clean_preview) > 120:
        clean_preview = clean_preview[:117].rstrip() + "…"
    lines = [
        "📢 <b>Выберите получателей рассылки</b>",
        "",
        f"Сообщение: <i>{html.quote(clean_preview or 'без текста')}</i>",
        "",
        f"Выбрано: <b>{selected_count}</b> из {total_count}",
    ]
    if total_count and selected_count == total_count:
        lines.append("Сейчас выбраны все ученики. Можно снять лишние отметки вручную.")
    elif selected_count == 0:
        lines.append("Сейчас никто не выбран. Отметьте хотя бы одного получателя.")
    else:
        lines.append("Можно точечно снять или добавить нужных получателей кнопками ниже.")
    return "\n".join(lines)


def build_broadcast_send_result_text(sent_count: int, total_count: int) -> str:
    failed = max(total_count - sent_count, 0)
    if failed == 0:
        return (
            "✅ <b>Рассылка завершена</b>\n\n"
            f"Сообщение доставлено <b>{sent_count}</b> из <b>{total_count}</b> получателей."
        )
    return (
        "⚠️ <b>Рассылка завершена частично</b>\n\n"
        f"Доставлено: <b>{sent_count}</b> из <b>{total_count}</b>\n"
        f"Не доставлено: <b>{failed}</b>\n\n"
        "Обычно это значит, что часть пользователей давно не открывала бота или бот им недоступен."
    )


def build_admin_freeze_queue_text(pending_count: int) -> str:
    if pending_count == 0:
        return (
            "❄️ <b>Заявки на заморозку</b>\n\n"
            "Сейчас активных заявок нет. Как только кто-то отправит новую, она появится здесь."
        )
    return (
        "❄️ <b>Заявки на заморозку</b>\n\n"
        f"Сейчас на рассмотрении: <b>{pending_count}</b>.\n"
        "Карточки заявок отправлены ниже отдельными сообщениями, чтобы их было удобно обработать по одной."
    )


def build_admin_freeze_request_text(lesson_id: int, student_name: str, reason_label: str, submitted_at: str) -> str:
    return (
        f"❄️ <b>Заявка #{lesson_id}</b>\n\n"
        f"👤 Ученик: <b>{html.quote(student_name)}</b>\n"
        f"🧭 Причина: <b>{html.quote(reason_label)}</b>\n"
        f"🕒 Отправлена: <b>{html.quote(submitted_at)}</b>\n\n"
        "Выберите решение ниже."
    )


def build_admin_freeze_action_text(action: str, student_name: str, lesson_date: str | None = None) -> str:
    if action == "approve":
        lines = [
            "✅ <b>Заявка одобрена</b>",
            "",
            f"👤 Ученик: <b>{html.quote(student_name)}</b>",
        ]
        if lesson_date:
            lines.append(f"📅 Замороженное занятие: <b>{html.quote(lesson_date)}</b>")
        lines.append("")
        lines.append("Ученик уже получил подтверждение.")
        return "\n".join(lines)
    return (
        "❌ <b>Заявка отклонена</b>\n\n"
        f"👤 Ученик: <b>{html.quote(student_name)}</b>\n\n"
        "Ученик уже получил уведомление, что занятия продолжаются по обычному графику."
    )


def build_admin_dashboard_text(snapshot: dict, ops_status: dict, last_sync_label) -> str:
    if isinstance(last_sync_label, dict):
        last_sync_label = (
            last_sync_label.get("synced_at_local")
            or last_sync_label.get("synced_at")
            or "ещё не запускался"
        )
    elif not last_sync_label:
        last_sync_label = "ещё не запускался"
    scheduler = html.quote(str(ops_status.get("scheduler", "unknown")))
    lines = [
        "🛠 <b>Панель администратора</b>",
        "",
        "Короткая сводка на сейчас:",
        f"👥 Активных учеников: <b>{snapshot.get('active_students', 0)}</b>",
        f"📅 Уроков сегодня: <b>{snapshot.get('lessons_today', 0)}</b>",
        f"💰 Нулевой баланс: <b>{snapshot.get('unpaid_students', 0)}</b>",
        f"📭 Без ближайших уроков: <b>{snapshot.get('students_without_upcoming_lessons', 0)}</b>",
        f"❄️ Заморозки на рассмотрении: <b>{snapshot.get('pending_freezes', 0)}</b>",
        f"📚 Активных ДЗ: <b>{snapshot.get('active_homework', 0)}</b>",
        "",
        "Система:",
        f"⏱ Scheduler: <b>{scheduler}</b>",
        f"🗓 Последний sync: <b>{html.quote(last_sync_label)}</b>",
        "",
        "Ниже выберите рабочую зону: ученики, учебный процесс, коммуникации, аккаунт или система.",
    ]
    return "\n".join(lines)


def build_admin_students_page_text(students: list, page: int, page_size: int) -> str:
    if not students:
        return ADMIN_STUDENTS_EMPTY_TEXT

    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = students[start:start + page_size]

    lines = [f"👥 <b>Список учеников</b> ({len(students)} чел.)"]
    if total_pages > 1:
        lines.append(f"Страница <b>{page + 1}/{total_pages}</b>")

    for index, student in enumerate(page_items, start + 1):
        lesson_label = format_short_datetime(student.get("next_lesson_date")) if student.get("next_lesson_date") else "не назначен"
        freshness = student_freshness_badge(student.get("first_lesson_date"))
        lines.extend([
            "",
            f"{index}. <b>{html.quote(student['full_name'])}</b>",
            f"{lesson_format_icon(student.get('lesson_format'))} {lesson_format_label(student.get('lesson_format'))} · "
            f"{html.quote(student.get('language') or '—')} {html.quote(student.get('level') or '—')} · "
            f"{lesson_balance_label(student.get('lesson_balance'))} · {lesson_label} · {freshness}",
        ])

    lines.extend([
        "",
        "Откройте карточку ниже, чтобы перейти к действиям и настройкам.",
    ])
    return "\n".join(lines)


def build_admin_student_card_text(student, balance: int, next_lesson: datetime | None) -> str:
    reminders = reminder_status_label(student.get("lesson_reminders"))
    freshness = student_freshness_badge(student.get("first_lesson_date"))
    return "\n".join([
        f"👤 <b>{html.quote(student['full_name'])}</b>",
        "",
        f"🏷 Статус: <b>{freshness}</b>",
        f"{lesson_format_icon(student.get('lesson_format'))} Формат: <b>{lesson_format_label(student.get('lesson_format'))}</b>",
        f"🗣 Обращение: <b>{speech_style_label(student.get('speech_style'))}</b>",
        f"🌍 Язык: <b>{html.quote(student.get('language') or '—')}</b>",
        f"📘 Уровень: <b>{html.quote(student.get('level') or '—')}</b>",
        f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(next_lesson) if next_lesson else 'не назначен')}</b>",
        f"🔔 Напоминания: <b>{html.quote(reminders)}</b>",
        f"🆔 Telegram ID: <code>{student['telegram_id']}</code>",
        "",
        "Ниже отдельно вынесены действия и настройки, чтобы карточка оставалась читаемой.",
    ])


def build_admin_payments_text(student_name: str, balance: int, payments: list) -> str:
    if not payments:
        return "\n".join([
            f"💰 <b>Оплаты: {student_name}</b>",
            "",
            f"Сейчас на балансе: <b>{lesson_balance_label(balance)}</b>",
            "История оплат пока пустая.",
        ])

    lines = [
        f"💰 <b>Оплаты: {student_name}</b>",
        "",
        f"Текущий баланс: <b>{lesson_balance_label(balance)}</b>",
        "",
        "Последние оплаты:",
    ]
    for index, payment in enumerate(payments, 1):
        lines.extend([
            "",
            f"{index}. <b>{int(payment['amount'])} ₽</b> · {payment['lessons_count']} ур.",
            f"   📅 {format_date(payment.get('payment_date'))}",
            f"   🎓 Остаток: {lesson_balance_label(payment.get('lessons_remaining'))}",
        ])
    lines.extend(["", "Ниже можно быстро удалить лишнюю запись, если это нужно."])
    return "\n".join(lines)


def build_admin_homework_list_text(items: list) -> str:
    if not items:
        return "📋 <b>Активные ДЗ</b>\n\nСейчас активных заданий нет."
    lines = [f"📋 <b>Активные ДЗ</b> ({len(items)})"]
    for item in items:
        lines.extend([
            "",
            f"• <b>{html.quote(item['full_name'])}</b>",
            f"  📝 {item['title']}",
            f"  📅 До {format_date(item.get('deadline'))}",
        ])
    lines.extend(["", "Выберите задание ниже, если нужно удалить его из списка."])
    return "\n".join(lines)
