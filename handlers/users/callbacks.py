import logging

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from data.config import load_teacher_info
from handlers.users.admin_sections.common import restore_admin_view
from keyboards.inline import (
    freeze_keyboard, back_to_menu_keyboard, back_to_admin_keyboard,
    cancel_fsm_keyboard, make_freeze_confirm_keyboard, FREEZE_REASON_LABELS,
    payment_keyboard, make_homework_filter_keyboard,
    make_homework_list_keyboard, make_contacts_keyboard,
    make_notifications_keyboard, profile_keyboard,
    parent_profile_keyboard,
    make_level_test_link_keyboard, make_self_delete_confirm_keyboard,
    make_teacher_reply_keyboard, make_write_to_student_keyboard, make_back_button_keyboard,
    get_main_menu_keyboard,
)
from states.registration import FreezeConfirm, StudentReply
from utils.db_api.postgresql import Database
from utils.reschedule import decode_reschedule_slot, format_reschedule_slot_label
from utils.ui_text import (
    ACTION_CANCELLED_TEXT,
    MAIN_MENU_TEXT,
    REGISTRATION_REQUIRED_TEXT,
    build_action_result_text,
    build_contacts_text,
    build_freeze_confirm_text,
    build_freeze_intro_text,
    build_freeze_success_text,
    build_homework_text,
    build_notifications_text,
    build_payment_text,
    build_profile_text,
    build_requisites_text,
    build_schedule_text,
    build_self_delete_success_text,
    build_self_delete_warning_text,
)

logger = logging.getLogger(__name__)

router = Router()

REPLY_CONTEXT_LABELS = {
    "homework": "по домашнему заданию",
    "payment": "по оплате",
    "lesson": "по ближайшему занятию",
    "broadcast": "по сообщению от преподавателя",
    "freeze": "по заморозке",
    "teacher_message": "по сообщению от преподавателя",
    "review": "по просьбе оставить отзыв",
    "general": "без уточнения темы",
}

LESSON_PRESENCE_LABELS = {
    "on_time": "✅ Буду вовремя",
    "late": "⏱ Немного задержусь",
}


def _build_self_delete_warning(user, snapshot: dict) -> str:
    return build_self_delete_warning_text(user, snapshot)


# ─── Global navigation ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'back_to_menu', StateFilter('*'))
async def back_to_menu(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    user = await db.get_user(callback_query.from_user.id)
    role = user.get("role") if user else None
    await callback_query.message.edit_text(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu_keyboard(role, is_platform_admin=callback_query.from_user.id == config.ADMIN_ID),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'cancel_fsm', StateFilter('*'))
async def cancel_fsm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    state_data = await state.get_data()
    await state.clear()
    is_admin = callback_query.from_user.id == config.ADMIN_ID
    if is_admin:
        restored = await restore_admin_view(
            callback_query.bot,
            db,
            state_data.get("admin_origin_chat_id"),
            state_data.get("admin_origin_message_id"),
            state_data.get("admin_return_view"),
        )
        if restored:
            await callback_query.answer("Действие отменено.")
            return
    await callback_query.message.edit_text(
        ACTION_CANCELLED_TEXT,
        reply_markup=back_to_admin_keyboard if is_admin else back_to_menu_keyboard,
    )
    await callback_query.answer()


# ─── Main menu callbacks ──────────────────────────────────────────────────────

async def _render_profile_screen(message: types.Message, db: Database, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        await message.edit_text(REGISTRATION_REQUIRED_TEXT, reply_markup=back_to_menu_keyboard)
        return

    balance = await db.get_student_lesson_balance(user_id)
    next_lessons = await db.get_active_lessons(user_id) if user["role"] == "student" else []
    next_lesson = next_lessons[0]["lesson_date"] if next_lessons and next_lessons[0].get("lesson_date") else None

    children = None
    if user["role"] == "parent":
        children = await db.get_parent_children(user_id)

    text = build_profile_text(
        user,
        balance,
        next_lesson=next_lesson,
        reminders=user.get("lesson_reminders"),
        children=children,
    )
    if user["role"] == "student":
        keyboard = profile_keyboard
    elif user["role"] == "parent":
        keyboard = parent_profile_keyboard
    else:
        keyboard = back_to_menu_keyboard
    await message.edit_text(text, reply_markup=keyboard)


async def _render_notifications_screen(message: types.Message, db: Database, user_id: int):
    user = await db.get_user(user_id)
    reminders = (user.get("lesson_reminders") or "enabled") if user else "enabled"
    await message.edit_text(
        build_notifications_text(reminders),
        reply_markup=make_notifications_keyboard(reminders),
    )


async def _render_homework_list(message: types.Message, db: Database, user_id: int, status: str = "active"):
    items = await db.get_student_homework(user_id, status)
    await message.edit_text(
        build_homework_text(items, status),
        reply_markup=make_homework_list_keyboard(items, status) if items else make_homework_filter_keyboard(status),
    )

@router.callback_query(lambda c: c.data in ['schedule', 'freeze', 'payment', 'profile'])
async def process_menu_choice(callback_query: types.CallbackQuery, db: Database):
    choice = callback_query.data
    user_id = callback_query.from_user.id

    user = await db.get_user(user_id)

    if not user:
        await callback_query.message.edit_text(
            REGISTRATION_REQUIRED_TEXT,
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    if choice == 'schedule':
        lessons = await db.get_active_lessons(user_id)
        text = build_schedule_text(lessons)
        await callback_query.message.edit_text(text, reply_markup=back_to_menu_keyboard)

    elif choice == 'freeze':
        lessons = await db.get_active_lessons(user_id)
        active_count = len(lessons)
        if not active_count:
            await callback_query.message.edit_text(
                build_action_result_text(
                    "Заморозка сейчас не нужна",
                    "У вас нет активных занятий, которые можно отправить на заморозку.",
                    next_step="Когда появятся новые уроки, к этой кнопке можно будет вернуться в любой момент.",
                    icon="ℹ️",
                ),
                reply_markup=back_to_menu_keyboard,
            )
        else:
            await callback_query.message.edit_text(
                build_freeze_intro_text(active_count),
                reply_markup=freeze_keyboard,
            )

    elif choice == 'payment':
        payments = await db.get_student_payments(user_id)
        balance = await db.get_student_lesson_balance(user_id)
        text = build_payment_text(balance, payments)
        await callback_query.message.edit_text(text, reply_markup=payment_keyboard)

    elif choice == 'profile':
        await _render_profile_screen(callback_query.message, db, user_id)

    await callback_query.answer()


def _build_profile_text(user, balance: int) -> str:
    return build_profile_text(user, balance, reminders=user.get("lesson_reminders"))


async def _build_reply_context_label(db: Database, context_key: str, entity_id: int | None) -> str:
    if context_key == "homework" and entity_id:
        hw = await db.get_homework_by_id(entity_id)
        if hw:
            return f"по домашнему заданию «{html.quote(hw['title'])}»"
    return REPLY_CONTEXT_LABELS.get(context_key, "без уточнения темы")


@router.callback_query(lambda c: c.data.startswith('reply:'), StateFilter('*'))
async def start_student_reply(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Ответ доступен только ученикам.", show_alert=True)
        return

    if not config.ADMIN_ID:
        await callback_query.answer("ADMIN_ID не настроен.", show_alert=True)
        return

    parts = callback_query.data.split(':')
    context_key = parts[1] if len(parts) > 1 else "general"
    entity_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    context_label = await _build_reply_context_label(db, context_key, entity_id)

    await state.clear()
    await state.set_state(StudentReply.waiting_for_message)
    await state.update_data(
        reply_context_key=context_key,
        reply_entity_id=entity_id,
        reply_context_label=context_label,
    )

    await callback_query.message.answer(
        "✉️ Напишите сообщение для преподавателя.\n\n"
        f"Контекст: <b>{context_label}</b>\n\n"
        "Можно отправить текст, фото, документ, голосовое, GIF или стикер.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(StudentReply.waiting_for_message))
async def process_student_reply_message(message: types.Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "student":
        await state.clear()
        await message.answer(
            "⚠️ Ответ сейчас доступен только зарегистрированным ученикам.",
            reply_markup=back_to_menu_keyboard,
        )
        return

    if not config.ADMIN_ID:
        await state.clear()
        await message.answer(
            "⚠️ ADMIN_ID не настроен. Сообщение не отправлено.",
            reply_markup=back_to_menu_keyboard,
        )
        return

    data = await state.get_data()
    context_label = data.get("reply_context_label", "без уточнения темы")
    student_name = html.quote(user["full_name"] or message.from_user.full_name or str(message.from_user.id))
    username = f"@{message.from_user.username}" if message.from_user.username else "—"

    await message.bot.send_message(
        config.ADMIN_ID,
        "✉️ <b>Ответ от ученика</b>\n\n"
        f"👤 {student_name}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"🔗 Username: {html.quote(username)}\n"
        f"🧭 Контекст: <b>{context_label}</b>",
        reply_markup=make_write_to_student_keyboard(message.from_user.id),
    )
    try:
        await message.copy_to(config.ADMIN_ID)
    except Exception:
        fallback_text = message.text or message.caption or "[Сообщение без текста]"
        await message.bot.send_message(
            config.ADMIN_ID,
            f"⚠️ Не удалось переслать оригинал автоматически.\n\n{html.quote(fallback_text)}",
        )

    await state.clear()
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            "Преподаватель получит его в ближайшее время.",
            next_step="Если нужно, можно вернуться в меню и продолжить работу с ботом.",
        ),
        reply_markup=back_to_menu_keyboard,
    )


# ─── Contacts ─────────────────────────────────────────────────────────────────

def _build_contacts_text(info: dict, show_address: bool = False) -> str:
    return build_contacts_text(info, show_address=show_address)


def _get_level_test_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("level_test_url", "") or info.get("level_test_url", "")


def _get_project_site_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("project_site_url", "") or info.get("project_site_url", "")


@router.callback_query(lambda c: c.data == 'contacts')
async def process_contacts(callback_query: types.CallbackQuery, db: Database):
    info = load_teacher_info()
    user = await db.get_user(callback_query.from_user.id)
    text = _build_contacts_text(info, show_address=bool(user))
    contacts = info.get('contacts', {})
    kb = make_contacts_keyboard(
        booking_url=contacts.get('booking_url', ''),
        calendar_url=contacts.get('calendar_url', ''),
        vk_call_url=contacts.get('vk_call', ''),
        google_meet_url=contacts.get('google_meet', ''),
        website_url=_get_project_site_url(info),
    )
    await callback_query.message.edit_text(text, reply_markup=kb)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('level_test:'))
async def process_level_test_choice(callback_query: types.CallbackQuery):
    action = callback_query.data.split(':', 1)[1]
    url = _get_level_test_url()

    if action == "now":
        if url:
            await callback_query.message.edit_text(
                build_action_result_text(
                    "Тест уровня",
                    "Отлично. Откройте тест по кнопке ниже, когда будете готовы.",
                    next_step="Если что-то будет непонятно, можно написать преподавателю.",
                    icon="🧪",
                ),
                reply_markup=make_level_test_link_keyboard(url, back_callback="profile"),
            )
        else:
            await callback_query.message.edit_text(
                build_action_result_text(
                    "Тест уровня",
                    "Ссылка на тест пока не добавлена.",
                    next_step="Напишите преподавателю, и он пришлёт её отдельно.",
                    icon="🧪",
                ),
                reply_markup=make_back_button_keyboard("◀️ Назад в профиль", "profile"),
            )
    elif action == "later":
        await callback_query.message.edit_text(
            build_action_result_text(
                "Можно пройти позже",
                "Кнопка <b>🧪 Тест уровня</b> останется в профиле.",
                next_step="Когда захотите, вернитесь к ней в любое время.",
                icon="🕒",
            ),
            reply_markup=make_back_button_keyboard("◀️ Назад в профиль", "profile"),
        )
    else:
        await callback_query.message.edit_text(
            build_action_result_text(
                "Тест можно не проходить",
                "Ничего страшного. Если передумаете, преподаватель поможет с выбором следующего шага.",
                icon="🙏",
            ),
            reply_markup=make_back_button_keyboard("◀️ Назад в профиль", "profile"),
        )

    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'profile:delete_me')
async def process_profile_delete_me(callback_query: types.CallbackQuery, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user:
        await callback_query.message.edit_text(
            "⚠️ Вы не зарегистрированы. Используйте /start.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    if user["role"] not in {"student", "parent"}:
        await callback_query.message.edit_text(
            "ℹ️ Самоудаление сейчас доступно ученикам и родителям.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    snapshot = await db.get_user_deletion_snapshot(callback_query.from_user.id)
    await callback_query.message.edit_text(
        _build_self_delete_warning(user, snapshot),
        reply_markup=make_self_delete_confirm_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'self_delete:confirm')
async def process_self_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user:
        await callback_query.message.edit_text(
            "⚠️ Профиль уже удалён. Используйте /start для новой регистрации.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    if user["role"] not in {"student", "parent"}:
        await callback_query.message.edit_text(
            "ℹ️ Самоудаление сейчас доступно ученикам и родителям.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    await db.delete_user_fully(callback_query.from_user.id)

    await callback_query.message.edit_text(
        build_self_delete_success_text(user["role"]),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


# ─── Requisites ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in {'requisites', 'payment:requisites'})
async def process_requisites(callback_query: types.CallbackQuery, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    back_keyboard = (
        make_back_button_keyboard("◀️ Назад к оплате", "payment")
        if callback_query.data == "payment:requisites"
        else back_to_menu_keyboard
    )

    if not user:
        await callback_query.message.edit_text(
            "🔒 Реквизиты доступны только зарегистрированным пользователям.\n\n"
            "Используйте /start для регистрации.",
            reply_markup=back_keyboard,
        )
        await callback_query.answer()
        return

    info = load_teacher_info()
    await callback_query.message.edit_text(
        build_requisites_text(info.get("requisites", {})),
        reply_markup=back_keyboard,
    )
    await callback_query.answer()


# ─── Freeze: two-step confirmation ───────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith('freeze:'))
async def process_freeze_reason(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    reason = callback_query.data.split(':')[1]
    label = FREEZE_REASON_LABELS.get(reason, reason)
    active_lessons = await db.get_active_lessons(callback_query.from_user.id)
    active_count = len(active_lessons)

    if not active_count:
        await callback_query.message.edit_text(
            build_action_result_text(
                "Заморозка сейчас не нужна",
                "У вас нет активных занятий, которые можно отправить на заморозку.",
                next_step="Если ситуация изменится, вы сможете вернуться к этой кнопке позже.",
                icon="ℹ️",
            ),
            reply_markup=back_to_menu_keyboard,
        )
        await state.clear()
        await callback_query.answer()
        return

    await state.set_state(FreezeConfirm.waiting_for_confirm)
    await state.update_data(freeze_reason=reason, freeze_active_count=active_count)

    await callback_query.message.edit_text(
        build_freeze_confirm_text(label, active_count),
        reply_markup=make_freeze_confirm_keyboard(reason),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('freeze_confirm:'),
    StateFilter(FreezeConfirm.waiting_for_confirm),
)
async def process_freeze_confirm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    reason = callback_query.data.split(':', 1)[1]
    user_id = callback_query.from_user.id
    state_data = await state.get_data()
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else None

    async with db.pool.acquire() as conn:
        if account_id is not None:
            active = await conn.fetch(
                """
                SELECT id
                FROM lessons
                WHERE student_id = $1
                  AND account_id = $2
                  AND status = 'active'
                """,
                user_id,
                account_id,
            )
        else:
            active = await conn.fetch(
                "SELECT id FROM lessons WHERE student_id = $1 AND status = 'active'",
                user_id,
            )
        if not active:
            await callback_query.message.edit_text(
                build_action_result_text(
                    "Заморозка сейчас не нужна",
                    "У вас нет активных занятий, которые можно отправить на заморозку.",
                    icon="ℹ️",
                ),
                reply_markup=back_to_menu_keyboard,
            )
            await state.clear()
            await callback_query.answer()
            return

        if account_id is not None:
            await conn.execute(
                """
                UPDATE lessons
                SET status = 'freeze_pending',
                    freeze_reason = $1,
                    freeze_start_date = CURRENT_TIMESTAMP
                WHERE student_id = $2
                  AND account_id = $3
                  AND status = 'active'
                """,
                reason,
                user_id,
                account_id,
            )
        else:
            await conn.execute(
                """
                UPDATE lessons
                SET status = 'freeze_pending',
                    freeze_reason = $1,
                    freeze_start_date = CURRENT_TIMESTAMP
                WHERE student_id = $2 AND status = 'active'
                """,
                reason,
                user_id,
            )

    await state.clear()

    label = FREEZE_REASON_LABELS.get(reason, reason)
    admin_id = config.ADMIN_ID
    if admin_id:
        await callback_query.bot.send_message(
            admin_id,
            f"❄️ <b>Новая заявка на заморозку!</b>\n\n"
            f"👤 Ученик: {html.quote(callback_query.from_user.full_name)}\n"
            f"Причина: {label}\n"
            f"Затронуто занятий: {len(active)}",
        )

    await callback_query.message.edit_text(
        build_freeze_success_text(label, state_data.get("freeze_active_count", len(active))),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


# ─── Homework (student) ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'homework')
async def process_homework(callback_query: types.CallbackQuery, db: Database):
    await _render_homework_list(callback_query.message, db, callback_query.from_user.id, status="active")
    await callback_query.answer()


@router.callback_query(lambda c: c.data in ('hw:active', 'hw:done'))
async def process_homework_list(callback_query: types.CallbackQuery, db: Database):
    user_id = callback_query.from_user.id
    status = callback_query.data.split(':')[1]
    await _render_homework_list(callback_query.message, db, user_id, status=status)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('hw_done:'))
async def process_homework_done(callback_query: types.CallbackQuery, db: Database):
    user_id = callback_query.from_user.id
    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw['student_id'] != user_id or hw['status'] != 'active':
        await callback_query.message.edit_text(
            "ℹ️ Задание не найдено или уже отмечено как выполненное.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    await db.mark_homework_done(hw_id, user_id)
    title = html.quote(hw['title'])

    student = await db.get_user(user_id)
    student_name = html.quote(student['full_name']) if student else str(user_id)
    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"✅ <b>ДЗ выполнено!</b>\n\n"
                f"👤 {student_name}\n"
                f"📝 {title}",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о выполненном ДЗ %s: %s", hw_id, exc)

    await _render_homework_list(callback_query.message, db, user_id, status="active")
    await callback_query.answer("Отметил как выполненное.")


@router.callback_query(lambda c: c.data.startswith('lesson_presence:'))
async def process_lesson_presence(callback_query: types.CallbackQuery, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return

    parts = callback_query.data.split(':')
    if len(parts) != 3 or parts[1] not in LESSON_PRESENCE_LABELS:
        await callback_query.answer("Некорректный ответ.", show_alert=True)
        return

    status = parts[1]
    lesson_id = int(parts[2]) if parts[2].isdigit() else None
    if not lesson_id:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return

    account_id = db.require_account_id() if hasattr(db, "require_account_id") else None
    async with db.pool.acquire() as conn:
        if account_id is not None:
            lesson = await conn.fetchrow(
                "SELECT * FROM lessons WHERE id = $1 AND account_id = $2",
                lesson_id,
                account_id,
            )
        else:
            lesson = await conn.fetchrow("SELECT * FROM lessons WHERE id = $1", lesson_id)
    if not lesson or lesson["student_id"] != callback_query.from_user.id:
        await callback_query.answer("Этот урок недоступен.", show_alert=True)
        return

    lesson_time = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else "дата уточняется"
    student_name = html.quote(user["full_name"] or callback_query.from_user.full_name or str(callback_query.from_user.id))
    answer_label = LESSON_PRESENCE_LABELS[status]

    await callback_query.message.edit_reply_markup(
        reply_markup=make_teacher_reply_keyboard("lesson", lesson_id),
    )
    await callback_query.message.answer(
        build_action_result_text(
            "Ответ принят",
            f"Статус по занятию: <b>{answer_label}</b>.",
            next_step="Спасибо за подтверждение.",
        ),
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"📩 <b>Ответ по занятию</b>\n\n"
                f"👤 Ученик: {student_name}\n"
                f"📅 Урок: <b>{lesson_time}</b>\n"
                f"Статус: <b>{answer_label}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу статус по занятию %s: %s", lesson_id, exc)

    await callback_query.answer("Ответ отправлен.")


@router.callback_query(lambda c: c.data.startswith('reschedule_pick:'))
async def process_reschedule_pick(callback_query: types.CallbackQuery, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return
    if hasattr(db, "has_capability") and not await db.has_capability("smart_reschedule"):
        await callback_query.message.edit_text(
            build_action_result_text(
                "Умный перенос сейчас недоступен",
                "Для этого аккаунта функция переноса по слотам не активирована.",
                next_step="Если нужно, можно написать преподавателю вручную.",
                icon="🔒",
            ),
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    token = callback_query.data.split(':', 1)[1]
    try:
        slot = decode_reschedule_slot(token)
    except ValueError:
        await callback_query.answer("Слот не распознан.", show_alert=True)
        return

    slot_label = format_reschedule_slot_label(slot)
    await callback_query.message.edit_reply_markup(
        reply_markup=make_teacher_reply_keyboard("broadcast"),
    )
    await callback_query.message.answer(
        build_action_result_text(
            "Вариант переноса отправлен",
            f"Я передал преподавателю, что вам подходит <b>{html.quote(slot_label)}</b>.",
            next_step="Если нужно, можно ещё написать преподавателю вручную.",
        ),
        reply_markup=back_to_menu_keyboard,
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                "🗓 <b>Выбран вариант переноса</b>\n\n"
                f"👤 Ученик: <b>{html.quote(user['full_name'])}</b>\n"
                f"📅 Предпочтительный слот: <b>{html.quote(slot_label)}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу выбранный слот переноса: %s", exc)

    await callback_query.answer("Вариант отправлен.")


# ─── Notifications settings ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'notif:manage')
async def process_notif_manage(callback_query: types.CallbackQuery, db: Database):
    await _render_notifications_screen(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('notif:'))
async def process_notif_action(callback_query: types.CallbackQuery, db: Database):
    action = callback_query.data.split(':', 1)[1]
    user_id = callback_query.from_user.id

    from datetime import timedelta, date
    if action == 'disable':
        await db.set_lesson_reminders(user_id, 'disabled')
    elif action == 'pause_week':
        until = (date.today() + timedelta(weeks=1)).strftime('%d.%m.%Y')
        await db.set_lesson_reminders(user_id, f'paused_until:{until}')
    elif action == 'enable':
        await db.set_lesson_reminders(user_id, 'enabled')
    else:
        await callback_query.answer()
        return

    await _render_notifications_screen(callback_query.message, db, user_id)
    await callback_query.answer()
