from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data.config import is_internal_test_account
from handlers.users.admin_sections.common import (
    extract_broadcast_payload,
    get_message_origin,
    is_admin,
    q,
    restore_admin_view,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_admin_lesson_formats_keyboard,
    make_admin_speech_styles_keyboard,
    make_admin_student_danger_confirm_keyboard,
    make_deactivate_confirm_keyboard,
    make_delete_confirm_keyboard,
    make_student_select_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import AdminAddStudent, AdminManageStudent, AdminWriteToStudent
from utils.db_api.postgresql import Database
from utils.domain_errors import BusinessRuleError
from utils.ui_text import (
    ADMIN_LESSON_FORMATS_EMPTY_TEXT,
    ADMIN_NO_ACTIVE_STUDENTS_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    ADMIN_SPEECH_STYLES_EMPTY_TEXT,
    ADMIN_STUDENTS_EMPTY_TEXT,
    build_action_result_text,
    lesson_balance_label,
    lesson_format_icon,
    lesson_format_label,
    reminder_status_label,
    student_freshness_badge,
)
from utils.speech import normalize_speech_style, speech_style_label

router = Router()

ADMIN_STUDENTS_PAGE_SIZE = 5
STUDENT_CARD_MAIN = "main"
STUDENT_CARD_ACTIONS = "actions"
STUDENT_CARD_SETTINGS = "settings"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _student_back_buttons(student_id: int, page: int) -> list[list[InlineKeyboardButton]]:
    return [
        [_btn("◀️ К карточке", f"admin:student_card:{student_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
    ]


def _student_card_keyboard(student_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✉️ Написать", f"admin:write_to_student:{student_id}:{page}"),
            _btn("💰 Оплаты", f"admin:student_payments:{student_id}:{page}"),
        ],
        [
            _btn("⚡ Действия", f"admin:student_actions:{student_id}:{page}"),
            _btn("⚙️ Настройки", f"admin:student_settings:{student_id}:{page}"),
        ],
        *_student_back_buttons(student_id, page),
    ])


def _student_actions_keyboard(student_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("➕ Урок", f"admin:quick:add_lesson:{student_id}:{page}"),
            _btn("💳 Добавить оплату", f"admin:quick:add_payment:{student_id}:{page}"),
        ],
        [
            _btn("📚 Задать ДЗ", f"admin:quick:add_homework:{student_id}:{page}"),
            _btn("✉️ Написать", f"admin:write_to_student:{student_id}:{page}"),
        ],
        *_student_back_buttons(student_id, page),
    ])


def _student_settings_keyboard(student_id: int, page: int, lesson_format: str, speech_style: str) -> InlineKeyboardMarkup:
    is_offline = (lesson_format or "online").strip().lower() == "offline"
    format_label = "🏠 Формат: очно" if is_offline else "💻 Формат: онлайн"
    toggle_to = "online" if is_offline else "offline"
    toggle_label = "Переключить на онлайн" if is_offline else "Переключить на очно"
    speech_label = speech_style_label(speech_style)
    next_speech = "informal" if (speech_style or "formal").strip().lower() == "formal" else "formal"
    next_speech_label = "на ты" if (speech_style or "formal").strip().lower() == "formal" else "на Вы"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn(f"{format_label} · {toggle_label}", f"admin:student_format:{student_id}:{page}:{toggle_to}"),
            _btn(f"🗣 Обращение: {speech_label} · {next_speech_label}", f"admin:student_speech_style:{student_id}:{page}:{next_speech}"),
        ],
        [
            _btn("🗑 Деактивировать", f"admin:student_deactivate_prompt:{student_id}:{page}"),
            _btn("💀 Удалить навсегда", f"admin:student_delete_prompt:{student_id}:{page}"),
        ],
        *_student_back_buttons(student_id, page),
    ])


def _student_page_title(page: int, total_pages: int | None = None) -> str:
    if total_pages and total_pages > 1:
        return f"Страница <b>{page + 1}/{total_pages}</b>"
    return ""


def _build_student_summary_line(student, index: int) -> str:
    language = q(student.get("language") or "—")
    level = q(student.get("level") or "—")
    full_name = q(student["full_name"])
    balance = lesson_balance_label(student.get("lesson_balance"))
    format_icon = lesson_format_icon(student.get("lesson_format"))
    freshness = student_freshness_badge(student.get("first_lesson_date"))
    next_lesson = student.get("next_lesson_date")
    if next_lesson:
        lesson_line = f"📅 Следующий урок: {next_lesson.strftime('%d.%m %H:%M')}"
    else:
        lesson_line = "📅 Нет запланированных уроков"
    return (
        f"<b>{index}. {full_name}</b>\n"
        f"{format_icon} {language} {level} · {balance} · {freshness}\n"
        f"{lesson_line}"
    )


def _student_list_keyboard(page_items: list[dict], page: int, total_pages: int, start: int) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{start + offset}. {student['full_name']}", f"admin:student_card:{student['telegram_id']}:{page}")]
        for offset, student in enumerate(page_items, start=1)
    ]
    if total_pages > 1:
        rows.append([
            _btn("⬅️", f"admin:students:page:{page - 1}") if page > 0 else _btn("·", "noop"),
            _btn(f"{page + 1}/{total_pages}", "noop"),
            _btn("➡️", f"admin:students:page:{page + 1}") if page < total_pages - 1 else _btn("·", "noop"),
        ])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _students_overview_keyboard(students: list[dict], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(students) + ADMIN_STUDENTS_PAGE_SIZE - 1) // ADMIN_STUDENTS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_STUDENTS_PAGE_SIZE
    page_items = students[start:start + ADMIN_STUDENTS_PAGE_SIZE]
    return _student_list_keyboard(page_items, page, total_pages, start)


async def _render_admin_students_page(message: types.Message, db: Database, page: int = 0):
    students = await db.get_students_overview()

    if not students:
        await message.edit_text(ADMIN_STUDENTS_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    total_pages = max(1, (len(students) + ADMIN_STUDENTS_PAGE_SIZE - 1) // ADMIN_STUDENTS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ADMIN_STUDENTS_PAGE_SIZE
    page_items = students[start:start + ADMIN_STUDENTS_PAGE_SIZE]

    lines = [
        f"👥 <b>Список учеников</b> ({len(students)} чел.)",
    ]
    page_title = _student_page_title(page, total_pages)
    if page_title:
        lines.append(page_title)
    lines.extend([
        "",
        "Откройте карточку кнопкой ниже. В списке оставлены только короткие ориентиры.",
    ])
    for index, student in enumerate(page_items, start + 1):
        lines.extend(["", _build_student_summary_line(student, index)])

    await message.edit_text(
        "\n".join(lines),
        reply_markup=_student_list_keyboard(page_items, page, total_pages, start),
    )


async def _render_admin_student_card(message: types.Message, db: Database, student_id: int, page: int, section: str = STUDENT_CARD_MAIN):
    student = await db.get_user(student_id)

    if not student or student["role"] != "student" or student["is_active"] is False:
        await message.edit_text(
            "⚠️ Ученик не найден или уже деактивирован.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    balance = await db.get_student_lesson_balance(student_id)
    next_lessons = await db.get_active_lessons(student_id)
    next_lesson = next_lessons[0]["lesson_date"] if next_lessons and next_lessons[0].get("lesson_date") else None

    lesson_format = student.get("lesson_format") or "online"
    speech_style = student.get("speech_style") or "formal"

    if section == STUDENT_CARD_ACTIONS:
        title = "⚡ <b>Быстрые действия</b>"
        body = "Здесь собраны действия без настроек и опасных шагов."
        keyboard = _student_actions_keyboard(student_id, page)
    elif section == STUDENT_CARD_SETTINGS:
        title = "⚙️ <b>Настройки ученика</b>"
        body = (
            f"Формат: <b>{lesson_format_label(lesson_format)}</b>\n"
            f"Обращение: <b>{speech_style_label(speech_style)}</b>\n"
            "Ниже можно переключить формат, обращение и опасные сценарии."
        )
        keyboard = _student_settings_keyboard(student_id, page, lesson_format, speech_style)
    else:
        title = f"👤 <b>{q(student['full_name'])}</b>"
        body = "\n".join([
            f"🏷 Статус: <b>{student_freshness_badge(student.get('first_lesson_date'))}</b>",
            f"{lesson_format_icon(lesson_format)} Формат: <b>{lesson_format_label(lesson_format)}</b>",
            f"🗣 Обращение: <b>{speech_style_label(speech_style)}</b>",
            f"🌍 Язык: <b>{q(student.get('language') or '—')}</b>",
            f"📘 Уровень: <b>{q(student.get('level') or '—')}</b>",
            f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
            f"📅 Ближайший урок: <b>{q(next_lesson.strftime('%d.%m.%Y %H:%M') if next_lesson else 'не назначен')}</b>",
            f"🔔 Напоминания: <b>{q(reminder_status_label(student.get('lesson_reminders')))}</b>",
            f"🆔 Telegram ID: <code>{student['telegram_id']}</code>",
        ])
        keyboard = _student_card_keyboard(student_id, page)

    await message.edit_text(
        "\n".join([title, "", body]),
        reply_markup=keyboard,
    )


def _write_to_student_result_keyboard(student_id: int, page: int | None):
    if page is not None:
        return make_back_button_keyboard("◀️ К карточке ученика", f"admin:student_card:{student_id}:{page}")
    return back_to_admin_keyboard


async def _render_admin_lesson_formats(message: types.Message, db: Database):
    students = await db.get_all_students()
    if not students:
        await message.edit_text(ADMIN_LESSON_FORMATS_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    offline = [s for s in students if (s.get("lesson_format") or "online") == "offline"]
    online = [s for s in students if (s.get("lesson_format") or "online") != "offline"]

    lines = [
        "🏫 <b>Формат занятий</b>",
        "",
        f"🏠 Очные: <b>{len(offline)}</b>",
        f"💻 Онлайн: <b>{len(online)}</b>",
        "",
    ]
    if offline:
        lines.append("Очные ученики:")
        for student in offline:
            lines.append(f"• {q(student['full_name'])}")
        lines.append("")
    lines.append("Нажмите на ученика ниже, чтобы переключить формат.")

    await message.edit_text(
        "\n".join(lines),
        reply_markup=make_admin_lesson_formats_keyboard(students),
    )


async def _render_admin_speech_styles(message: types.Message, db: Database):
    students = await db.get_all_students()
    if not students:
        await message.edit_text(ADMIN_SPEECH_STYLES_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    formal = [s for s in students if normalize_speech_style(s.get("speech_style")) == "formal"]
    informal = [s for s in students if normalize_speech_style(s.get("speech_style")) == "informal"]

    lines = [
        "🗣 <b>Обращение с учениками</b>",
        "",
        f"🫱 На Вы: <b>{len(formal)}</b>",
        f"🤝 На ты: <b>{len(informal)}</b>",
        "",
    ]
    if formal:
        lines.append("Сейчас на Вы:")
        for student in formal:
            lines.append(f"• {q(student['full_name'])}")
        lines.append("")
    lines.append("Нажмите на ученика ниже, чтобы переключить обращение.")

    await message.edit_text(
        "\n".join(lines),
        reply_markup=make_admin_speech_styles_keyboard(students),
    )


@router.callback_query(lambda c: c.data == "admin:students")
async def admin_students(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_students_page(callback_query.message, db, page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:page:"))
async def admin_students_page(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    page = int(callback_query.data.split(":")[3])
    await _render_admin_students_page(callback_query.message, db, page=page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_card:"))
async def admin_student_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_card(callback_query.message, db, int(student_id_str), int(page_str), STUDENT_CARD_MAIN)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_actions:"))
async def admin_student_actions(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_card(callback_query.message, db, int(student_id_str), int(page_str), STUDENT_CARD_ACTIONS)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_settings:"))
async def admin_student_settings(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_card(callback_query.message, db, int(student_id_str), int(page_str), STUDENT_CARD_SETTINGS)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:write_to_student:"))
async def admin_write_to_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_return_view=f"admin:student_card:{student_id}:{page}" if page is not None else None,
        admin_origin_chat_id=origin_chat_id if page is not None else None,
        admin_origin_message_id=origin_message_id if page is not None else None,
        admin_student_card_page=page,
    )
    await state.set_state(AdminWriteToStudent.waiting_for_message)
    await callback_query.message.answer(
        f"✉️ Отправьте сообщение для ученика <b>{q(student['full_name'])}</b>.\n\n"
        "Можно отправить текст, GIF, стикер, фото, документ, голосовое или видео.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWriteToStudent.waiting_for_message))
async def admin_write_to_student_send(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Отправка доступна только администратору.", reply_markup=back_to_admin_keyboard)
        return

    payload = extract_broadcast_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Отправьте текст, GIF, стикер или другое сообщение, которое нужно переслать ученику.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data["student_id"]
    page = data.get("admin_student_card_page")
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await state.clear()
        await message.answer("⚠️ Ученик не найден.", reply_markup=back_to_admin_keyboard)
        return

    try:
        if payload["mode"] == "copy":
            await message.bot.copy_message(
                chat_id=student_id,
                from_chat_id=payload["source_chat_id"],
                message_id=payload["source_message_id"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
        else:
            await message.bot.send_message(
                student_id,
                payload["text"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
    except Exception:
        await message.answer(
            "⚠️ Не удалось отправить сообщение ученику. Попробуйте ещё раз.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            f"Ученик: <b>{q(student['full_name'])}</b>.",
            next_step="При необходимости можно сразу отправить ещё одно сообщение из карточки ученика.",
        ),
        reply_markup=_write_to_student_result_keyboard(student_id, page),
    )


@router.callback_query(lambda c: c.data.startswith("admin:student_format:"))
async def admin_student_format_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_student_card(callback_query.message, db, student_id, page, STUDENT_CARD_SETTINGS)
    await callback_query.answer(f"Формат переключён: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_speech_style:"))
async def admin_student_speech_style_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_student_card(callback_query.message, db, student_id, page, STUDENT_CARD_SETTINGS)
    await callback_query.answer(f"Обращение переключено: {speech_style_label(target_style)}")


@router.callback_query(lambda c: c.data == "admin:lesson_formats")
async def admin_lesson_formats(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_lesson_formats(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:speech_styles")
async def admin_speech_styles(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_speech_styles(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:lesson_format_toggle:"))
async def admin_lesson_format_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_lesson_formats(callback_query.message, db)
    await callback_query.answer(f"Переключено: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:speech_style_toggle:"))
async def admin_speech_style_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_speech_styles(callback_query.message, db)
    await callback_query.answer(f"Переключено: {speech_style_label(target_style)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_prompt:"))
async def admin_student_deactivate_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    await callback_query.message.edit_text(
        f"🗑 <b>Деактивировать ученика {name}?</b>\n\n"
        "Ученик потеряет доступ к боту, но история занятий и оплат сохранится.",
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_deactivate_confirm:{student_id}:{page}",
            f"admin:student_settings:{student_id}:{page}",
            "✅ Подтвердить деактивацию",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_confirm:"))
async def admin_student_deactivate_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    students = await db.get_students_overview()
    await callback_query.message.edit_text(
        build_action_result_text(
            "Ученик деактивирован",
            f"Профиль <b>{name}</b> отключён, а история занятий и оплат сохранена.",
            next_step="При необходимости ученика можно снова добавить или зарегистрировать заново.",
        ),
        reply_markup=(
            _students_overview_keyboard(students, page)
            if students
            else back_to_admin_keyboard
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_prompt:"))
async def admin_student_delete_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    snapshot = await db.get_user_deletion_snapshot(student_id)

    await callback_query.message.edit_text(
        f"💀 <b>Удалить ученика {name}?</b>\n\n"
        f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
        f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
        f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n\n"
        "Это действие необратимо.",
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_delete_confirm:{student_id}:{page}",
            f"admin:student_settings:{student_id}:{page}",
            "💀 Подтвердить удаление",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_confirm:"))
async def admin_student_delete_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    students = await db.get_students_overview()
    if not students:
        await callback_query.message.edit_text(ADMIN_STUDENTS_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
    else:
        page = min(page, max(0, (len(students) - 1) // ADMIN_STUDENTS_PAGE_SIZE))
        await callback_query.message.edit_text(
            build_action_result_text(
                "Ученик удалён",
                f"Профиль <b>{name}</b> полностью удалён из базы.",
                next_step="Если человек снова запустит /start, он пройдёт регистрацию заново.",
            ),
            reply_markup=_students_overview_keyboard(students, page),
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:deactivate_student")
async def admin_deactivate_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(ADMIN_NO_ACTIVE_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return
    await state.set_state(AdminManageStudent.waiting_for_student)
    await state.update_data(action="deactivate")
    await callback_query.message.edit_text(
        "🗑 <b>Деактивировать ученика</b>\n\nВыберите ученика:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:delete_student")
async def admin_delete_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(ADMIN_NO_ACTIVE_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return
    await state.set_state(AdminManageStudent.waiting_for_student)
    await state.update_data(action="delete")
    await callback_query.message.edit_text(
        "💀 <b>Удалить ученика</b>\n\nВыберите ученика для полного удаления:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("select_student:"), StateFilter(AdminManageStudent.waiting_for_student))
async def admin_select_student_manage(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    data = await state.get_data()
    action = data.get("action")
    await state.clear()

    if action == "delete":
        snapshot = await db.get_user_deletion_snapshot(student_id)
        await callback_query.message.edit_text(
            f"💀 <b>Удалить ученика {name}?</b>\n\n"
            "⚠️ Будут удалены все занятия, платежи и данные.\n"
            f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
            f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
            f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n"
            f"🧭 Calendar-связей: <b>{snapshot.get('calendar_links', 0)}</b>\n\n"
            "После этого ученик сможет зарегистрироваться заново.",
            reply_markup=make_delete_confirm_keyboard(student_id),
        )
    else:
        await callback_query.message.edit_text(
            f"🗑 Деактивировать ученика <b>{name}</b>?\n\n"
            "Ученик не сможет пользоваться ботом. История платежей и занятий сохранится.",
            reply_markup=make_deactivate_confirm_keyboard(student_id),
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("deactivate_confirm:"))
async def admin_deactivate_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    await callback_query.message.edit_text(
        f"✅ Ученик <b>{name}</b> деактивирован.\n\nИстория сохранена.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("delete_confirm:"))
async def admin_delete_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    await callback_query.message.edit_text(
        f"💀 Ученик <b>{name}</b> полностью удалён.\n\n"
        "При следующем /start он пройдёт регистрацию заново.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:add_student")
async def admin_add_student_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminAddStudent.waiting_for_name)
    await callback_query.message.edit_text(
        "👤 <b>Добавить ученика</b>\n\n"
        "Введите полное имя ученика.\n"
        "Лучше использовать тот вариант, который потом будет в Google Calendar:\n\n"
        "Например: <code>Иван Петров</code>",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddStudent.waiting_for_name))
async def admin_add_student_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ Имя не может быть пустым.", reply_markup=cancel_fsm_keyboard)
        return
    await state.update_data(full_name=name)
    await state.set_state(AdminAddStudent.waiting_for_telegram_id)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "Теперь введите Telegram ID ученика.\n\n"
        "Если ID неизвестен — введите <code>0</code>, тогда ученик сможет "
        "войти сам через /start и его данные обновятся автоматически.",
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminAddStudent.waiting_for_telegram_id))
async def admin_add_student_id(message: types.Message, state: FSMContext, db: Database):
    try:
        telegram_id = int((message.text or "").strip())
        if telegram_id < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Введите числовой Telegram ID или <code>0</code> если неизвестен.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    full_name = data["full_name"]

    if telegram_id == 0:
        await message.answer(
            "⚠️ Добавление без Telegram ID пока не поддерживается.\n\n"
            "Самый простой путь сейчас:\n"
            "1. Попросите ученика открыть бота.\n"
            "2. Пусть он отправит <code>/start</code> и зарегистрируется сам.\n"
            "3. После этого вернитесь в список учеников или добавьте занятие.",
            reply_markup=back_to_admin_keyboard,
        )
        await state.clear()
        return

    existing = await db.get_user(telegram_id)
    if existing:
        await state.clear()
        await message.answer(
            f"⚠️ Пользователь с ID <code>{telegram_id}</code> уже есть в базе:\n"
            f"<b>{q(existing['full_name'])}</b> ({q(existing['role'])})",
            reply_markup=back_to_admin_keyboard,
        )
        return

    async with db.pool.acquire() as conn:
        internal = is_internal_test_account(full_name=full_name, telegram_id=telegram_id)
        account_id = db.require_account_id()
        if hasattr(db, "ensure_student_capacity"):
            try:
                await db.ensure_student_capacity(
                    telegram_id,
                    is_internal=internal,
                    account_id=account_id,
                )
            except BusinessRuleError as exc:
                await state.clear()
                await message.answer(
                    f"⚠️ {q(str(exc))}",
                    reply_markup=back_to_admin_keyboard,
                )
                return
        identity_id = None
        if hasattr(db, "ensure_global_identity"):
            identity = await db.ensure_global_identity(
                telegram_id=telegram_id,
                full_name=full_name,
                username=None,
            )
            identity_id = identity["id"] if identity else None
        await conn.execute(
            """
            INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role, is_internal_account)
            VALUES ($1, $2, $3, $4, NULL, 'student', $5)
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = EXCLUDED.identity_id,
                full_name = EXCLUDED.full_name,
                role = EXCLUDED.role,
                is_internal_account = EXCLUDED.is_internal_account,
                is_active = true
            """,
            account_id, identity_id, telegram_id, full_name, internal,
        )
    await db.ensure_account_user(telegram_id, "student")

    await state.clear()
    internal_line = (
        "\n⚙️ Аккаунт помечен как внутренний тестовый и исключён из рабочей логики."
        if internal else ""
    )
    await message.answer(
        f"✅ <b>Ученик добавлен!</b>\n\n"
        f"👤 Имя: {q(full_name)}\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n\n"
        f"Теперь можно запустить /sync — занятия из Calendar привяжутся к этому ученику."
        f"{internal_line}",
        reply_markup=back_to_admin_keyboard,
    )
