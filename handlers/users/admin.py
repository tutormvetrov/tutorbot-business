import logging
from datetime import datetime

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import (
    get_message_origin,
    is_admin as _is_admin,
    q as _q,
    restore_admin_view,
)
from keyboards.inline import (
    admin_communication_keyboard,
    admin_education_keyboard,
    admin_service_keyboard,
    admin_students_keyboard,
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_back_button_keyboard,
    make_freeze_action_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lessons_manage_keyboard,
    make_paywall_keyboard,
    make_student_select_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import AdminAddLesson, AdminManageLessons
from utils.capabilities import capability_label
from utils.db_api.postgresql import Database
from utils.google_calendar import (
    delete_calendar_event,
    format_sync_report_html,
    load_last_sync_report,
    sync_calendar_to_db,
)
from utils.observability import load_ops_status
from utils.product_ui import build_paywall_text
from utils.speech import choose_form
from utils.ui_text import (
    ADMIN_ADD_LESSON_INVALID_TEXT,
    ADMIN_ADD_LESSON_PROMPT_TEXT,
    ADMIN_ADD_LESSON_START_TEXT,
    build_admin_freeze_action_text,
    build_admin_freeze_queue_text,
    build_admin_freeze_request_text,
    build_admin_dashboard_text,
    ADMIN_COMMUNICATION_CATEGORY_TEXT,
    ADMIN_EDUCATION_CATEGORY_TEXT,
    ADMIN_HOME_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    ADMIN_SERVICE_CATEGORY_TEXT,
    ADMIN_STUDENTS_CATEGORY_TEXT,
    ADMIN_SYNC_ERROR_HINT,
    ADMIN_SYNC_IN_PROGRESS_TEXT,
)

logger = logging.getLogger(__name__)

router = Router()

def _btn(text: str, callback_data: str):
    return types.InlineKeyboardButton(text=text, callback_data=callback_data)


def _current_account_id(db: Database) -> int | None:
    return db.require_account_id() if hasattr(db, "require_account_id") else None


admin_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👥 Ученики", "admin:cat:students"), _btn("📚 Учебный процесс", "admin:cat:education")],
    [_btn("📢 Коммуникации", "admin:cat:communication"), _btn("🏢 Аккаунт", "admin:cat:account")],
    [_btn("🛠 Система", "admin:cat:system")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

admin_account_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📈 Аналитика", "admin:analytics"), _btn("🧾 Тариф", "admin:billing")],
    [_btn("👥 Команда", "admin:team"), _btn("🔗 Инвайты", "admin:invites")],
    [_btn("🆘 Диагностика", "admin:support"), _btn("🏢 Аккаунт", "workspace:selector")],
    [_btn("◀️ К панели", "admin:home")],
])

admin_system_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🚦 Быстрый запуск", "admin:setup"), _btn("🔄 Синхронизация Calendar", "admin:sync:system")],
    [_btn("🧭 Алиасы Calendar", "admin:calendar_aliases"), _btn("📋 Отчёт синхронизации", "admin:calendar_report")],
    [_btn("🏥 Здоровье бота", "admin:health"), _btn("🎨 Оформление и экраны", "admin:ui")],
    [_btn("📝 Сообщения для отладки", "admin:notes")],
    [_btn("◀️ К панели", "admin:home")],
])

ADMIN_CATEGORY_VIEWS = {
    "students": (
        ADMIN_STUDENTS_CATEGORY_TEXT,
        admin_students_keyboard,
    ),
    "education": (
        ADMIN_EDUCATION_CATEGORY_TEXT,
        admin_education_keyboard,
    ),
    "communication": (
        ADMIN_COMMUNICATION_CATEGORY_TEXT,
        admin_communication_keyboard,
    ),
    "account": (
        "🏢 <b>Аккаунт</b>\n\n"
        "Биллинг, команда, инвайты, аналитика и поддержка собраны в одном месте.",
        admin_account_keyboard,
    ),
    "system": (
        "🛠 <b>Система</b>\n\n"
        "Быстрый запуск, Calendar, оформление, здоровье и служебные заметки.",
        admin_system_keyboard,
    ),
    "service": (
        ADMIN_SERVICE_CATEGORY_TEXT,
        admin_service_keyboard,
    ),
}


def _return_view_from_source(source: str | None) -> str:
    if source == "education":
        return "admin:cat:education"
    if source == "students":
        return "admin:cat:students"
    if source == "communication":
        return "admin:cat:communication"
    if source == "account":
        return "admin:cat:account"
    if source == "system":
        return "admin:cat:system"
    if source == "service":
        return "admin:cat:service"
    return "admin:home"


def _back_label_for_view(view: str) -> str:
    return {
        "admin:cat:account": "◀️ К аккаунту",
        "admin:cat:system": "◀️ К системе",
        "admin:cat:service": "◀️ К сервису",
        "admin:home": "◀️ К панели",
    }.get(view, "◀️ Вернуться")


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view and return_view.startswith("admin:student_card:"):
        parts = return_view.split(":")
        if len(parts) == 4 and student_id is not None:
            return make_admin_context_keyboard(student_id, int(parts[3]))
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


async def render_admin_home(message: types.Message, db: Database):
    snapshot = await db.get_admin_dashboard_snapshot()
    ops_status = await load_ops_status()
    sync_report = await load_last_sync_report(_current_account_id(db))
    await message.edit_text(
        build_admin_dashboard_text(snapshot, ops_status, sync_report),
        reply_markup=admin_keyboard,
    )


async def render_admin_category(message: types.Message, category: str):
    view = ADMIN_CATEGORY_VIEWS.get(category)
    if not view:
        await message.edit_text("⚠️ Раздел не найден.", reply_markup=back_to_admin_keyboard)
        return

    text, keyboard = view
    await message.edit_text(text, reply_markup=keyboard)


async def render_brand_tone_settings(message: types.Message):
    await message.edit_text(
        "🎨 <b>Оформление перенесено</b>\n\n"
        "Тональность бренда теперь настраивается внутри нового конструктора экранов вместе с клиентскими текстами, контактами и меню.\n\n"
        "Откройте раздел <b>«Оформление и экраны»</b>, чтобы менять черновик и публиковать его без перезапуска бота.",
        reply_markup=make_back_button_keyboard("🎨 Открыть оформление", "admin:ui"),
    )


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command('admin'))
async def command_admin(message: types.Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    snapshot = await db.get_admin_dashboard_snapshot()
    ops_status = await load_ops_status()
    sync_report = await load_last_sync_report(_current_account_id(db))
    await message.answer(
        build_admin_dashboard_text(snapshot, ops_status, sync_report),
        reply_markup=admin_keyboard,
    )


# ─── /sync command ────────────────────────────────────────────────────────────

@router.message(Command('sync'))
async def command_sync(message: types.Message, db: Database):
    if not _is_admin(message.from_user.id):
        return
    if not await db.has_capability("calendar_sync"):
        snapshot = await db.get_account_billing_snapshot()
        await message.answer(
            build_paywall_text(capability_label("calendar_sync"), snapshot, snapshot["product"]),
            reply_markup=make_paywall_keyboard(back_callback="admin:cat:system", show_billing=True),
        )
        return
    await message.answer(ADMIN_SYNC_IN_PROGRESS_TEXT)
    try:
        report = await sync_calendar_to_db(db)
        await message.answer(format_sync_report_html(report))
    except Exception as e:
        logger.error(f"Ошибка синхронизации Calendar: {e}")
        await message.answer(
            f"❌ Ошибка синхронизации:\n<code>{e}</code>\n\n"
            f"{ADMIN_SYNC_ERROR_HINT}"
        )


# ─── Back to admin panel ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in {'back_to_admin', 'admin:home'}, StateFilter('*'))
async def back_to_admin(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await render_admin_home(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:cat:'))
async def admin_open_category(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    category = callback_query.data.split(':', 2)[2]
    view = ADMIN_CATEGORY_VIEWS.get(category)
    if not view:
        await callback_query.answer("Раздел не найден.", show_alert=True)
        return

    await render_admin_category(callback_query.message, category)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:sync'))
async def admin_sync_callback(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("calendar_sync"):
        snapshot = await db.get_account_billing_snapshot()
        await callback_query.message.edit_text(
            build_paywall_text(capability_label("calendar_sync"), snapshot, snapshot["product"]),
            reply_markup=make_paywall_keyboard(back_callback="admin:cat:system", show_billing=True),
        )
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    back_target = _return_view_from_source(source) if source else "admin:cat:system"
    back_keyboard = make_back_button_keyboard(_back_label_for_view(back_target), back_target)

    await callback_query.message.edit_text(
        ADMIN_SYNC_IN_PROGRESS_TEXT,
        reply_markup=back_keyboard,
    )
    try:
        report = await sync_calendar_to_db(db)
        await callback_query.message.edit_text(
            format_sync_report_html(report),
            reply_markup=back_keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка синхронизации Calendar: {e}")
        await callback_query.message.edit_text(
            f"❌ Ошибка синхронизации:\n<code>{e}</code>\n\n"
            f"{ADMIN_SYNC_ERROR_HINT}",
            reply_markup=back_keyboard,
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'admin:calendar_report')
async def admin_calendar_report(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("calendar_sync"):
        snapshot = await db.get_account_billing_snapshot()
        await callback_query.message.edit_text(
            build_paywall_text(capability_label("calendar_sync"), snapshot, snapshot["product"]),
            reply_markup=make_paywall_keyboard(back_callback="admin:cat:system", show_billing=True),
        )
        await callback_query.answer()
        return

    from handlers.users.admin_sections.calendar_aliases import _build_calendar_sync_snapshot_lines

    report = await load_last_sync_report(_current_account_id(db))
    snapshot_lines = _build_calendar_sync_snapshot_lines(report)
    await callback_query.message.edit_text(
        "\n".join(["📋 <b>Краткий отчёт синхронизации</b>", *snapshot_lines])
        if snapshot_lines else
        "📋 <b>Краткий отчёт синхронизации</b>\n\nОтчёта пока нет.",
        reply_markup=make_back_button_keyboard("◀️ К системе", "admin:cat:system"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'admin:brand_tone')
async def admin_brand_tone(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_brand_tone_settings(callback_query.message)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:brand_tone_set:'))
async def admin_brand_tone_set(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_brand_tone_settings(callback_query.message)
    await callback_query.answer("Используйте новый конструктор оформления.")


# ─── Add lesson ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith('admin:add_lesson'))
async def admin_add_lesson_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    students = await db.get_all_students()

    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_REGISTERED_STUDENTS_TEXT,
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await state.clear()
    await state.update_data(
        admin_return_view=_return_view_from_source(source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddLesson.waiting_for_lesson_student)
    await callback_query.message.edit_text(
        ADMIN_ADD_LESSON_START_TEXT,
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_lesson:'))
async def admin_add_lesson_quick(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, _, student_id_str, page_str = callback_query.data.split(':')
    student_id = int(student_id_str)
    page = int(page_str)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    await state.clear()
    await state.update_data(
        student_id=student_id,
        admin_return_view=f"admin:student_card:{student_id}:{page}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddLesson.waiting_for_lesson_date)
    await callback_query.message.edit_text(
        ADMIN_ADD_LESSON_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:'),
    StateFilter(AdminAddLesson.waiting_for_lesson_student),
)
async def admin_lesson_student_selected(callback_query: types.CallbackQuery, state: FSMContext):
    student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await state.set_state(AdminAddLesson.waiting_for_lesson_date)
    await callback_query.message.edit_text(
        ADMIN_ADD_LESSON_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddLesson.waiting_for_lesson_date))
async def admin_lesson_date_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        lesson_date = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(
            ADMIN_ADD_LESSON_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data['student_id']
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await db.add_lesson(student_id, lesson_date)

    student = await db.get_user(student_id)
    student_name = _q(student['full_name']) if student else str(student_id)

    await state.clear()
    await restore_admin_view(message.bot, db, origin_chat_id, origin_message_id, return_view)
    await message.answer(
        f"✅ <b>Занятие добавлено</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"📅 Дата: {lesson_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Карточка и сводка уже обновлены.",
        reply_markup=_reply_markup_for_return_view(return_view, student_id),
    )

# ─── Freeze requests ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'admin:freezes')
async def admin_freezes(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    pending = await db.get_pending_freeze_lessons()

    if not pending:
        await callback_query.message.edit_text(
            build_admin_freeze_queue_text(0),
            reply_markup=make_back_button_keyboard("◀️ К учебному процессу", "admin:cat:education"),
        )
        await callback_query.answer()
        return

    await callback_query.message.edit_text(
        build_admin_freeze_queue_text(len(pending)),
        reply_markup=make_back_button_keyboard("◀️ К учебному процессу", "admin:cat:education"),
    )

    from keyboards.inline import FREEZE_REASON_LABELS
    for lesson in pending:
        date_str = (
            lesson['freeze_start_date'].strftime('%d.%m.%Y %H:%M')
            if lesson.get('freeze_start_date') else '—'
        )
        reason_label = FREEZE_REASON_LABELS.get(lesson['freeze_reason'], lesson['freeze_reason'] or '—')
        await callback_query.bot.send_message(
            callback_query.from_user.id,
            build_admin_freeze_request_text(
                lesson['id'],
                lesson['full_name'],
                reason_label,
                date_str,
            ),
            reply_markup=make_freeze_action_keyboard(lesson['id']),
        )

    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('freeze_action:'))
async def admin_freeze_action(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, action, lesson_id_str = callback_query.data.split(':')
    lesson_id = int(lesson_id_str)

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow(
            'SELECT * FROM lessons WHERE id = $1 AND account_id = $2',
            lesson_id,
            db.require_account_id(),
        )

    if not lesson:
        await callback_query.message.edit_text(
            "⚠️ Заявка не найдена.",
            reply_markup=make_back_button_keyboard("◀️ К заморозкам", "admin:freezes"),
        )
        await callback_query.answer()
        return

    student_tid = lesson['student_id']
    student = await db.get_user(student_tid)
    student_name = student['full_name'] if student else str(student_tid)

    if action == 'approve':
        await db.approve_freeze(lesson_id)
        lesson_date_str = (
            lesson['lesson_date'].strftime('%d.%m.%Y %H:%M')
            if lesson.get('lesson_date') else "дата уточняется"
        )
        await callback_query.message.edit_text(
            build_admin_freeze_action_text("approve", student_name, lesson_date_str),
            reply_markup=make_back_button_keyboard("◀️ К заморозкам", "admin:freezes"),
        )
        await callback_query.bot.send_message(
            student_tid,
            f"✅ <b>{choose_form(student.get('speech_style') if student else None, 'Ваша', 'Твоя')} заявка на заморозку одобрена!</b>\n\n"
            f"📅 Занятие заморожено: <b>{lesson_date_str}</b>\n\n"
            f"Когда {choose_form(student.get('speech_style') if student else None, 'будете', 'будешь')} готовы продолжить — {choose_form(student.get('speech_style') if student else None, 'сообщите', 'сообщи')} преподавателю.",
            reply_markup=make_teacher_reply_keyboard("freeze"),
        )
    else:
        await db.reject_freeze(lesson_id)
        await callback_query.message.edit_text(
            build_admin_freeze_action_text("reject", student_name),
            reply_markup=make_back_button_keyboard("◀️ К заморозкам", "admin:freezes"),
        )
        await callback_query.bot.send_message(
            student_tid,
            f"❌ <b>{choose_form(student.get('speech_style') if student else None, 'Ваша', 'Твоя')} заявка на заморозку отклонена.</b>\n\n"
            f"Занятия продолжаются в обычном режиме. Если остались вопросы — {choose_form(student.get('speech_style') if student else None, 'свяжитесь', 'свяжись')} с преподавателем.",
            reply_markup=make_teacher_reply_keyboard("freeze"),
        )

    await callback_query.answer()


# ─── Manage lessons (delete) ──────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'admin:manage_lessons')
async def admin_manage_lessons_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            "⚠️ Нет зарегистрированных учеников.", reply_markup=back_to_admin_keyboard
        )
        await callback_query.answer()
        return

    await state.set_state(AdminManageLessons.waiting_for_student)
    await callback_query.message.edit_text(
        "🗑 <b>Удалить занятие</b>\n\nВыберите ученика:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:'),
    StateFilter(AdminManageLessons.waiting_for_student),
)
async def admin_manage_lessons_student_selected(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(':')[1])
    student = await db.get_user(student_id)
    name = _q(student['full_name']) if student else str(student_id)

    lessons = await db.get_non_completed_lessons(student_id)
    await state.clear()

    if not lessons:
        await callback_query.message.edit_text(
            f"📅 У <b>{name}</b> нет активных занятий для удаления.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await callback_query.message.edit_text(
        f"🗑 <b>Занятия ученика {name}</b>\n\nВыберите занятие для удаления:",
        reply_markup=make_lessons_manage_keyboard(lessons),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('lesson_delete_confirm:'))
async def admin_lesson_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    lesson_id = int(callback_query.data.split(':')[1])
    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow(
            'SELECT * FROM lessons WHERE id = $1 AND account_id = $2',
            lesson_id,
            db.require_account_id(),
        )

    if not lesson:
        await callback_query.message.edit_text("⚠️ Занятие не найдено.", reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return

    date_str = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else '—'
    has_calendar_link = bool(lesson.get('google_event_id'))
    calendar_hint = (
        "\n🗓 Событие связано с Google Calendar."
        "\nЕсли удалить только из базы бота, при следующей синхронизации урок может появиться снова.\n"
        if has_calendar_link else
        "\n🗓 Урок существует только в базе бота.\n"
    )
    await callback_query.message.edit_text(
        f"🗑 <b>Удалить занятие?</b>\n\n"
        f"📅 Дата: <b>{date_str}</b>\n"
        f"Статус: {lesson['status']}\n"
        f"{calendar_hint}\n"
        "⚠️ Действие необратимо.",
        reply_markup=make_lesson_delete_confirm_keyboard(lesson_id, can_delete_from_calendar=has_calendar_link),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('lesson_delete:'))
async def admin_lesson_delete(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    lesson_id = int(parts[1])
    delete_mode = parts[2] if len(parts) > 2 else "db"

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow(
            'SELECT * FROM lessons WHERE id = $1 AND account_id = $2',
            lesson_id,
            db.require_account_id(),
        )

    if not lesson:
        await callback_query.message.edit_text(
            "⚠️ Занятие не найдено.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    calendar_result = None
    if delete_mode == "calendar":
        google_event_id = lesson.get("google_event_id")
        if not google_event_id:
            await callback_query.message.edit_text(
                "⚠️ Это занятие не связано с Google Calendar. Можно удалить его только из базы бота.",
                reply_markup=back_to_admin_keyboard,
            )
            await callback_query.answer()
            return
        try:
            calendar_result = await delete_calendar_event(google_event_id)
        except Exception as exc:
            logger.error("Не удалось удалить событие %s из Google Calendar: %s", google_event_id, exc)
            await callback_query.message.edit_text(
                "⚠️ Не удалось удалить событие из Google Calendar.\n\n"
                "Занятие в базе бота пока оставлено без изменений.",
                reply_markup=back_to_admin_keyboard,
            )
            await callback_query.answer()
            return

    await db.delete_lesson(lesson_id)

    if delete_mode == "calendar":
        if calendar_result == "not_found":
            result_text = (
                "✅ <b>Занятие удалено из базы бота.</b>\n\n"
                "В Google Calendar связанное событие уже отсутствовало."
            )
        else:
            result_text = "✅ <b>Занятие удалено из базы бота и Google Calendar.</b>"
    else:
        result_text = (
            "✅ <b>Занятие удалено только из базы бота.</b>\n\n"
            "Если оно связано с Google Calendar, при следующей синхронизации запись может появиться снова."
        )

    await callback_query.message.edit_text(
        result_text,
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()
