from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.brand import BRAND_TONE_LABELS
from utils.speech import speech_style_icon, speech_style_label, speech_style_toggle_label
from utils.workspace import workspace_role_label


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


# ─── Navigation ───────────────────────────────────────────────────────────────

back_to_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ Главное меню", "back_to_menu")],
])

profile_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🔔 Управление уведомлениями", "notif:manage")],
    [_btn("🧪 Тест уровня", "level_test:now")],
    [_btn("🗑 Удалить себя из базы", "profile:delete_me")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

parent_profile_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🗑 Удалить себя из базы", "profile:delete_me")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✉️ Сообщить об оплате", "reply:payment"), _btn("💳 Реквизиты", "payment:requisites")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

back_to_admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ К панели", "admin:home")],
])

cancel_fsm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("❌ Отмена", "cancel_fsm")],
])

# ─── Registration ─────────────────────────────────────────────────────────────

role_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎓 Я ученик", "role:student")],
    [_btn("👨‍👩‍👧 Я родитель ученика", "role:parent")],
])

level_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("A1 — Начинающий", "level:A1"), _btn("A2 — Элементарный", "level:A2")],
    [_btn("B1 — Средний", "level:B1"), _btn("B2 — Выше среднего", "level:B2")],
    [_btn("C1 — Продвинутый", "level:C1"), _btn("C2 — Мастерство", "level:C2")],
    [_btn("🤷 Не знаю свой уровень", "level:unknown")],
])

# ─── Main menu ────────────────────────────────────────────────────────────────

main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📅 Расписание", "schedule"), _btn("📚 Домашние задания", "homework")],
    [_btn("❄️ Заморозка", "freeze"), _btn("💰 Оплата", "payment")],
    [_btn("👤 Профиль", "profile"), _btn("📞 Контакты", "contacts")],
    [_btn("🧭 Workspace", "workspace:selector"), _btn("💼 Продукт", "product:hub")],
    [_btn("💳 Реквизиты", "requisites")],
])

owner_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🛠 Панель", "admin:home"), _btn("🧭 Workspace", "workspace:selector")],
    [_btn("💼 Продукт", "product:hub"), _btn("👥 Команда", "product:team")],
    [_btn("👤 Профиль", "profile"), _btn("📞 Контакты", "contacts")],
    [_btn("💳 Реквизиты", "requisites")],
])

manager_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🛠 Панель", "admin:home"), _btn("🧭 Workspace", "workspace:selector")],
    [_btn("💼 Продукт", "product:hub"), _btn("👥 Команда", "product:team")],
    [_btn("📞 Контакты", "contacts"), _btn("💳 Реквизиты", "requisites")],
])

workspace_member_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🧭 Workspace", "workspace:selector"), _btn("💼 Продукт", "product:hub")],
    [_btn("👥 Команда", "product:team"), _btn("👤 Профиль", "profile")],
    [_btn("📞 Контакты", "contacts"), _btn("💳 Реквизиты", "requisites")],
])


def get_main_menu_keyboard(role: str | None, is_platform_admin: bool = False) -> InlineKeyboardMarkup:
    if is_platform_admin or role == "owner":
        return owner_main_keyboard
    if role == "manager":
        return manager_main_keyboard
    if role == "assistant":
        return workspace_member_keyboard
    return main_keyboard

# ─── Freeze ───────────────────────────────────────────────────────────────────

freeze_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🤒 Болезнь", "freeze:illness")],
    [_btn("✈️ Отпуск", "freeze:vacation")],
    [_btn("⚡ Форс-мажор", "freeze:force_majeure")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

FREEZE_REASON_LABELS = {
    "illness": "Болезнь",
    "vacation": "Отпуск",
    "force_majeure": "Форс-мажор",
}


def make_freeze_confirm_keyboard(reason: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("✅ Отправить заявку", f"freeze_confirm:{reason}"),
        _btn("◀️ Назад", "freeze"),
    ]])


# ─── Homework ─────────────────────────────────────────────────────────────────

def make_homework_filter_keyboard(active_status: str = "active") -> InlineKeyboardMarkup:
    active_label = "• Активные" if active_status == "active" else "📋 Активные"
    done_label = "• Выполненные" if active_status == "done" else "✅ Выполненные"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(active_label, "hw:active"), _btn(done_label, "hw:done")],
        [_btn("◀️ Главное меню", "back_to_menu")],
    ])


def make_notifications_keyboard(reminders: str = "enabled") -> InlineKeyboardMarkup:
    rows = []
    if reminders == "disabled":
        rows.append([_btn("🔔 Включить", "notif:enable")])
    elif reminders.startswith("paused_until:"):
        rows.append([_btn("🔔 Включить раньше", "notif:enable")])
        rows.append([_btn("❌ Отключить полностью", "notif:disable")])
    else:
        rows.append([_btn("🔕 Пауза на неделю", "notif:pause_week")])
        rows.append([_btn("❌ Отключить полностью", "notif:disable")])
    rows.append([_btn("◀️ Назад в профиль", "profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_item_keyboard(hw_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([_btn("✅ Отметить как выполненное", f"hw_done:{hw_id}")])
    rows.append([_btn("✉️ Написать по ДЗ", f"reply:homework:{hw_id}")])
    rows.append([_btn("◀️ К списку ДЗ", "homework")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_list_keyboard(items: list, status: str) -> InlineKeyboardMarkup:
    rows = []
    active_label = "• Активные" if status == "active" else "📋 Активные"
    done_label = "• Выполненные" if status == "done" else "✅ Выполненные"
    rows.append([
        _btn(active_label, "noop" if status == "active" else "hw:active"),
        _btn(done_label, "noop" if status == "done" else "hw:done"),
    ])
    if status == "active":
        for i, hw in enumerate(items, 1):
            title = hw["title"]
            label = f"✅ {i}. {title}" if len(title) <= 28 else f"✅ {i}. {title[:26]}…"
            rows.append([_btn(label, f"hw_done:{hw['id']}")])
        rows.append([_btn("✉️ Написать по домашке", "reply:homework")])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_teacher_reply_keyboard(context_key: str, entity_id: int | None = None) -> InlineKeyboardMarkup:
    callback_data = f"reply:{context_key}"
    if entity_id is not None:
        callback_data += f":{entity_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✉️ Ответить преподавателю", callback_data)],
    ])


def make_reschedule_offer_keyboard(slot_tokens: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[_btn(f"🗓 {label}", f"reschedule_pick:{token}")] for token, label in slot_tokens]
    rows.append([_btn("✉️ Написать преподавателю", "reply:broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_lesson_presence_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Буду вовремя", f"lesson_presence:on_time:{lesson_id}"),
            _btn("⏱ Немного задержусь", f"lesson_presence:late:{lesson_id}"),
        ],
        [_btn("✉️ Написать преподавателю", f"reply:lesson:{lesson_id}")],
    ])


# ─── Admin ────────────────────────────────────────────────────────────────────

admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👥 Ученики", "admin:cat:students"), _btn("📚 Учебный процесс", "admin:cat:education")],
    [_btn("📢 Коммуникации", "admin:cat:communication"), _btn("⚙️ Сервис", "admin:cat:service")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

admin_students_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📋 Список учеников", "admin:students"), _btn("👤 Добавить ученика", "admin:add_student")],
    [_btn("👥 Группы", "admin:groups")],
    [_btn("🏫 Формат занятий", "admin:lesson_formats"), _btn("🗣 Обращение", "admin:speech_styles")],
    [_btn("🗑 Деактивировать", "admin:deactivate_student"), _btn("💀 Полный сброс", "admin:delete_student")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_education_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("➕ Добавить занятие", "admin:add_lesson:education"), _btn("🗑 Удалить занятие", "admin:manage_lessons")],
    [_btn("💳 Добавить оплату", "admin:add_payment:education"), _btn("❄️ Заморозки", "admin:freezes")],
    [_btn("📚 Задать ДЗ", "admin:add_homework:education"), _btn("📋 Активные ДЗ", "admin:all_homework")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_communication_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📢 Рассылка", "admin:broadcast")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_service_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🔄 Синхронизация Calendar", "admin:sync:service")],
    [_btn("🧭 Алиасы Calendar", "admin:calendar_aliases")],
    [_btn("📋 Отчёт синхронизации", "admin:calendar_report")],
    [_btn("💳 Тарифы", "product:plans"), _btn("🪪 Подписка", "product:subscription")],
    [_btn("📈 Аналитика", "admin:analytics"), _btn("🧾 Billing", "admin:billing")],
    [_btn("👥 Команда", "admin:team"), _btn("🔗 Инвайты", "admin:invites")],
    [_btn("🆘 Support", "admin:support"), _btn("🧭 Workspace", "workspace:selector")],
    [_btn("🏥 Здоровье бота", "admin:health")],
    [_btn("🎨 Тональность бренда", "admin:brand_tone")],
    [_btn("📝 Сообщения для отладки", "admin:notes")],
    [_btn("◀️ К панели", "back_to_admin")],
])

broadcast_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🤒 Заболел — возможен перенос", "broadcast:illness")],
    [_btn("⚡ Форс-мажор — возможен перенос", "broadcast:force_majeure")],
    [_btn("🧪 Пригласить на тест уровня", "broadcast:level_test")],
    [_btn("✏️ Своё сообщение", "broadcast:custom")],
    [_btn("◀️ К панели", "back_to_admin")],
])


broadcast_preview_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ К выбору получателей", "bc_confirm")],
    [_btn("✏️ Изменить сообщение", "bc_edit_text")],
    [_btn("❌ Отмена", "cancel_fsm")],
])


def make_recipient_select_keyboard(students: list, selected_ids: set, segments_enabled: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for s in students:
        mark = "✅" if s["telegram_id"] in selected_ids else "☐"
        rows.append([_btn(f"{mark} {s['full_name']}", f"bc_toggle:{s['telegram_id']}")])
    if segments_enabled:
        rows.append([
            _btn("🎯 Без баланса", "bc_segment:zero_balance"),
            _btn("🎯 Без уроков", "bc_segment:no_upcoming"),
        ])
        rows.append([_btn("🎯 С родителями", "bc_segment:with_parents")])
    rows.append([_btn("☑️ Все", "bc_all"), _btn("✖️ Никто", "bc_none")])
    count = len(selected_ids)
    if count:
        rows.append([_btn(f"📤 Отправить ({count})", "bc_send")])
    else:
        rows.append([_btn("— выберите получателей —", "noop")])
    rows.append([_btn("◀️ К предпросмотру", "bc_back_preview")])
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_deactivate_confirm_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("✅ Деактивировать", f"deactivate_confirm:{student_id}"),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_delete_confirm_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("💀 Удалить навсегда", f"delete_confirm:{student_id}"),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_freeze_action_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Одобрить", f"freeze_action:approve:{lesson_id}"),
            _btn("❌ Отклонить", f"freeze_action:reject:{lesson_id}"),
        ],
        [_btn("◀️ К заявкам", "admin:freezes")],
    ])


def make_post_registration_keyboard(booking_url: str = "", website_url: str = "") -> InlineKeyboardMarkup:
    rows = []
    if booking_url:
        rows.append([_url_btn("📅 Записаться на пробный урок", booking_url)])
    if website_url:
        rows.append([_url_btn("↗️ Сайт и материалы", website_url)])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


level_test_prompt_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ Да, сейчас", "level_test:now")],
    [_btn("🕒 Да, позже", "level_test:later")],
    [_btn("🙏 Не нужно, спасибо", "level_test:no")],
])


def make_level_test_link_keyboard(url: str = "", back_callback: str = "back_to_menu") -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([_url_btn("🧪 Открыть тест уровня", url)])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_self_delete_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Да, удалить профиль", "self_delete:confirm")],
        [_btn("◀️ Назад в профиль", "profile")],
    ])


def make_write_to_student_keyboard(telegram_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    callback_data = f"admin:write_to_student:{telegram_id}"
    if page is not None:
        callback_data += f":{page}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("💰 Оплаты", f"admin:student_payments:{telegram_id}"),
            _btn("✉️ Написать", callback_data),
        ],
    ])


def make_admin_students_list_keyboard(students: list, page: int, page_size: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * page_size
    page_items = students[start:start + page_size]

    for offset, student in enumerate(page_items, start=1):
        index = start + offset
        label = f"{index}. {student['full_name']}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([
            _btn(label, f"admin:student_card:{student['telegram_id']}:{page}")
        ])

    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("⬅️", f"admin:students:page:{page - 1}"))
        else:
            nav_row.append(_btn("·", "noop"))
        nav_row.append(_btn(f"{page + 1}/{total_pages}", "noop"))
        if page < total_pages - 1:
            nav_row.append(_btn("➡️", f"admin:students:page:{page + 1}"))
        else:
            nav_row.append(_btn("·", "noop"))
        rows.append(nav_row)

    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_student_card_keyboard(
    telegram_id: int,
    page: int,
    lesson_format: str = "online",
    speech_style: str = "formal",
) -> InlineKeyboardMarkup:
    is_offline = lesson_format == "offline"
    format_label = "🏠 Формат: очно" if is_offline else "💻 Формат: онлайн"
    toggle_to = "online" if is_offline else "offline"
    toggle_label = "Переключить на онлайн" if is_offline else "Переключить на очно"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✉️ Написать", f"admin:write_to_student:{telegram_id}:{page}"),
            _btn("💰 Оплаты", f"admin:student_payments:{telegram_id}:{page}"),
        ],
        [
            _btn("➕ Урок", f"admin:quick:add_lesson:{telegram_id}:{page}"),
            _btn("💳 Добавить оплату", f"admin:quick:add_payment:{telegram_id}:{page}"),
        ],
        [_btn("📚 Задать ДЗ", f"admin:quick:add_homework:{telegram_id}:{page}")],
        [_btn(f"{format_label} · {toggle_label}", f"admin:student_format:{telegram_id}:{page}:{toggle_to}")],
        [_btn(
            f"🗣 Обращение: {speech_style_label(speech_style)} · {speech_style_toggle_label(speech_style)}",
            f"admin:student_speech_style:{telegram_id}:{page}:{'informal' if speech_style == 'formal' else 'formal'}",
        )],
        [_btn("🗑 Деактивировать", f"admin:student_deactivate_prompt:{telegram_id}:{page}")],
        [_btn("💀 Удалить навсегда", f"admin:student_delete_prompt:{telegram_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
        [_btn("◀️ К панели", "back_to_admin")],
    ])


def make_admin_lesson_formats_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        lesson_format = (student.get("lesson_format") or "online").strip().lower()
        is_offline = lesson_format == "offline"
        icon = "🏠" if is_offline else "💻"
        target = "online" if is_offline else "offline"
        target_label = "в онлайн" if is_offline else "в очно"
        label = f"{icon} {student['full_name']} · переключить {target_label}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:lesson_format_toggle:{student['telegram_id']}:{target}")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_speech_styles_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        current_style = (student.get("speech_style") or "formal").strip().lower()
        target = "informal" if current_style == "formal" else "formal"
        target_label = "на ты" if current_style == "formal" else "на Вы"
        label = f"{speech_style_icon(current_style)} {student['full_name']} · переключить {target_label}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:speech_style_toggle:{student['telegram_id']}:{target}")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_payment_delete_keyboard(student_id: int, payments: list, page: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for i, payment in enumerate(payments, 1):
        date_str = payment["payment_date"].strftime("%d.%m.%Y") if payment.get("payment_date") else "—"
        callback = f"payment_delete_confirm:{student_id}:{payment['id']}"
        if page is not None:
            callback += f":{page}"
        rows.append([
            _btn(
                f"🗑 {i}. {int(payment['amount'])} ₽ · {date_str}",
                callback,
            )
        ])
    if page is not None:
        rows.append([_btn("◀️ К карточке ученика", f"admin:student_card:{student_id}:{page}")])
    else:
        rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_payment_delete_confirm_keyboard(student_id: int, payment_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    delete_callback = f"payment_delete:{student_id}:{payment_id}"
    cancel_callback = f"admin:student_payments:{student_id}"
    if page is not None:
        delete_callback += f":{page}"
        cancel_callback += f":{page}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("🗑 Удалить оплату", delete_callback),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_contacts_keyboard(
    booking_url: str = "",
    calendar_url: str = "",
    vk_call_url: str = "",
    google_meet_url: str = "",
    website_url: str = "",
) -> InlineKeyboardMarkup:
    rows = []
    if vk_call_url:
        rows.append([_url_btn("📞 VK Звонок", vk_call_url)])
    if google_meet_url:
        rows.append([_url_btn("📹 Google Meet (VPN)", google_meet_url)])
    if calendar_url:
        rows.append([_url_btn("📅 Открыть расписание", calendar_url)])
    if booking_url:
        rows.append([_url_btn("📝 Записаться на урок", booking_url)])
    if website_url:
        rows.append([_url_btn("↗️ Сайт и материалы", website_url)])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_back_button_keyboard(label: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(label, callback_data)],
    ])


def make_product_hub_keyboard(show_team: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_btn("💳 Тарифы", "product:plans"), _btn("🧩 Что входит", "product:included")],
        [_btn("🪪 Подписка", "product:subscription")],
        [_btn("🚀 Попробовать / Продлить", "product:trial")],
    ]
    if show_team:
        rows.append([_btn("👥 Команда", "product:team"), _btn("🧭 Workspace", "workspace:selector")])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_product_screen_keyboard(back_callback: str = "product:hub", show_billing: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_btn("🧩 Что входит", "product:included"), _btn("💳 Тарифы", "product:plans")],
        [_btn("🪪 Подписка", "product:subscription"), _btn("🚀 Попробовать / Продлить", "product:trial")],
    ]
    if show_billing:
        rows.append([_btn("🧾 Billing", "admin:billing")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_paywall_keyboard(back_callback: str = "product:hub", show_billing: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_btn("💳 Тарифы", "product:plans"), _btn("🪪 Подписка", "product:subscription")],
        [_btn("🚀 Попробовать / Продлить", "product:trial")],
    ]
    if show_billing:
        rows.append([_btn("🧾 Billing", "admin:billing")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


admin_billing_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("Start · 30 дней", "admin:billing:activate:start:30"), _btn("Practice · 30 дней", "admin:billing:activate:practice:30")],
    [_btn("Studio · 30 дней", "admin:billing:activate:studio:30"), _btn("Practice · 90 дней", "admin:billing:activate:practice:90")],
    [_btn("➕ Trial +7 дней", "admin:billing:trial:7"), _btn("➕ Trial +14 дней", "admin:billing:trial:14")],
    [_btn("⛔ Отключить trial", "admin:billing:disable_trial")],
    [_btn("🧩 Overrides", "admin:billing:overrides")],
    [_btn("◀️ К сервису", "admin:cat:service")],
])


def make_billing_overrides_keyboard(enabled_capabilities: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for capability, label in [
        ("calendar_sync", "Calendar sync"),
        ("smart_reschedule", "Умный перенос"),
        ("weekly_digest", "Weekly digest"),
        ("segmented_broadcasts", "Сегментные рассылки"),
        ("groups", "Группы"),
        ("analytics_plus", "Analytics plus"),
        ("team_roles", "Командные роли"),
    ]:
        prefix = "✅" if capability in enabled_capabilities else "➕"
        rows.append([_btn(f"{prefix} {label}", f"admin:billing:override:{capability}")])
    rows.append([_btn("◀️ Назад к billing", "admin:billing")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_groups_keyboard(groups: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for group in groups:
        label = f"{group['name']} · {group.get('student_count', 0)}"
        rows.append([_btn(label, f"admin:group:view:{group['id']}")])
    rows.append([_btn("➕ Создать группу", "admin:groups:create")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_group_detail_keyboard(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("➕ Добавить ученика", f"admin:group:add_student:{group_id}")],
        [_btn("🗑 Архивировать группу", f"admin:group:delete:{group_id}")],
        [_btn("◀️ К группам", "admin:groups")],
    ])


def make_invites_keyboard(
    invites: list[dict],
    *,
    allow_manager_invite: bool = True,
    allow_assistant_invite: bool = True,
    back_callback: str = "admin:cat:service",
) -> InlineKeyboardMarkup:
    rows = []
    invite_buttons = []
    if allow_manager_invite:
        invite_buttons.append(_btn("➕ Менеджер", "admin:invite:create:manager"))
    if allow_assistant_invite:
        invite_buttons.append(_btn("➕ Ассистент", "admin:invite:create:assistant"))
    if invite_buttons:
        rows.append(invite_buttons)
    for invite in invites:
        rows.append([
            _btn(
                f"🗑 {invite.get('role', 'invite')} · #{invite['id']}",
                f"admin:invite:revoke:{invite['id']}",
            )
        ])
    rows.append([_btn("👥 Команда", "admin:team"), _btn("🆘 Support", "admin:support")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


support_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👥 Команда", "admin:team"), _btn("🔗 Инвайты", "admin:invites")],
    [_btn("🧾 Billing", "admin:billing"), _btn("🧭 Workspace", "workspace:selector")],
    [_btn("◀️ К сервису", "admin:cat:service")],
])


def make_team_keyboard(
    *,
    back_callback: str = "product:hub",
    allow_manager_invite: bool = False,
    allow_assistant_invite: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    invite_buttons = []
    if allow_manager_invite:
        invite_buttons.append(_btn("➕ Менеджер", "admin:invite:create:manager"))
    if allow_assistant_invite:
        invite_buttons.append(_btn("➕ Ассистент", "admin:invite:create:assistant"))
    if invite_buttons:
        rows.append(invite_buttons)
    if allow_manager_invite or allow_assistant_invite:
        rows.append([_btn("🔗 Инвайты", "admin:invites"), _btn("🧭 Workspace", "workspace:selector")])
    else:
        rows.append([_btn("🧭 Workspace", "workspace:selector")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_workspace_selector_keyboard(memberships: list[dict], current_account_id: int | None) -> InlineKeyboardMarkup:
    rows = []
    for membership in memberships:
        prefix = "✅" if membership.get("account_id") == current_account_id else "🏢"
        rows.append([
            _btn(
                f"{prefix} {membership.get('account_name', 'Workspace')} · {workspace_role_label(membership.get('role'))}",
                f"workspace:switch:{membership['account_id']}",
            )
        ])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_invite_join_keyboard(
    *,
    previous_account_id: int | None = None,
    previous_account_name: str | None = None,
    role: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [[_btn("✅ Открыть активный workspace", "back_to_menu")]]
    if previous_account_id is not None and previous_account_name:
        rows.append([
            _btn(
                f"↩️ Вернуться в {previous_account_name}",
                f"workspace:switch:{previous_account_id}",
            )
        ])
    if role in {"owner", "manager", "assistant"}:
        rows.append([_btn("👥 Команда", "product:team"), _btn("🧭 Workspace", "workspace:selector")])
    else:
        rows.append([_btn("🧭 Workspace", "workspace:selector")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_context_keyboard(student_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("◀️ Вернуться к карточке ученика", f"admin:student_card:{student_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
    ])


def make_admin_student_danger_confirm_keyboard(confirm_callback: str, cancel_callback: str, confirm_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(confirm_text, confirm_callback)],
        [_btn("❌ Отмена", cancel_callback)],
    ])


def make_student_select_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = [
        [_btn(s["full_name"], f"select_student:{s['telegram_id']}")]
        for s in students
    ]
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Admin notes ──────────────────────────────────────────────────────────────

admin_notes_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("➕ Новая заметка", "admin:notes:add")],
    [_btn("🧹 Очистить ленту", "admin:notes:clear")],
    [_btn("◀️ К сервису", "admin:cat:service")],
])


def make_homework_delete_keyboard(items: list) -> InlineKeyboardMarkup:
    rows = []
    for i, hw in enumerate(items, 1):
        deadline_str = hw["deadline"].strftime("%d.%m.%Y") if hw.get("deadline") else "—"
        label = f"🗑 {i}. {hw['full_name']} · до {deadline_str}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"hw_delete_confirm:{hw['id']}")])
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_delete_confirm_keyboard(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("🗑 Удалить ДЗ", f"hw_delete:{hw_id}"),
        _btn("❌ Отмена", "admin:all_homework"),
    ]])


# ─── Lesson management ────────────────────────────────────────────────────────

def make_lessons_manage_keyboard(lessons: list) -> InlineKeyboardMarkup:
    rows = []
    status_icons = {"active": "✅", "frozen": "❄️", "freeze_pending": "⏳"}
    for lesson in lessons:
        date_str = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else '—'
        icon = status_icons.get(lesson['status'], "•")
        rows.append([_btn(f"{icon} {date_str}", f"lesson_delete_confirm:{lesson['id']}")])
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_lesson_delete_confirm_keyboard(lesson_id: int, can_delete_from_calendar: bool = False) -> InlineKeyboardMarkup:
    rows = [[_btn("🗑 Удалить только из бота", f"lesson_delete:{lesson_id}:db")]]
    if can_delete_from_calendar:
        rows.append([_btn("🗓 Удалить из бота и Calendar", f"lesson_delete:{lesson_id}:calendar")])
    rows.append([_btn("❌ Отмена", "admin:manage_lessons")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_calendar_alias_student_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        count = student.get("alias_count", 0)
        label = f"{student['full_name']} ({count})" if count else student["full_name"]
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"calendar_alias_student:{student['telegram_id']}")])
    rows.append([_btn("◀️ К сервису", "admin:cat:service")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_calendar_alias_editor_keyboard(student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Очистить алиасы", f"calendar_aliases:clear:{student_id}")],
        [_btn("◀️ К списку учеников", "admin:calendar_aliases")],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])


def make_brand_tone_keyboard(current_tone: str) -> InlineKeyboardMarkup:
    rows = []
    for tone, label in BRAND_TONE_LABELS.items():
        prefix = "• " if tone == current_tone else ""
        rows.append([_btn(f"{prefix}{label.capitalize()}", f"admin:brand_tone_set:{tone}")])
    rows.append([_btn("◀️ К сервису", "admin:cat:service")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
