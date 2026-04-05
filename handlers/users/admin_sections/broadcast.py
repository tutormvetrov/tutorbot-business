from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from utils.account_ui import build_teacher_info_from_ui, resolve_ui_payload, ui_tone
from utils.brand import choose_tone_variant
from keyboards.inline import (
    back_to_admin_keyboard,
    broadcast_keyboard,
    broadcast_preview_keyboard,
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_paywall_keyboard,
    make_recipient_select_keyboard,
    make_reschedule_offer_keyboard,
    make_teacher_reply_keyboard,
)
from utils.scheduler import build_reschedule_slot_payloads
from states.registration import AdminBroadcast
from utils.db_api.postgresql import Database
from utils.capabilities import capability_label
from utils.product_ui import build_paywall_text
from utils.ui_text import (
    ADMIN_BROADCAST_EDIT_TEXT,
    ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT,
    ADMIN_BROADCAST_ENTER_TEXT,
    ADMIN_BROADCAST_START_TEXT,
    admin_broadcast_recipients_text,
    build_broadcast_preview_text,
    build_broadcast_send_result_text,
)

from handlers.users.admin_sections.common import (
    build_level_test_broadcast_text,
    extract_broadcast_payload,
    get_message_origin,
    is_admin,
)

router = Router()


def build_illness_broadcast_text(
    _: str | None = None,
    *,
    info: dict | None = None,
    tone: str | None = None,
) -> str:
    follow_up = choose_tone_variant(
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        tone=tone,
    )
    return (
        "⚠️ <b>Внимание</b>\n\n"
        "Сегодняшнего урока не будет.\n"
        "Причина: заболел.\n\n"
        f"{follow_up}"
    )


def build_force_majeure_broadcast_text(
    _: str | None = None,
    *,
    info: dict | None = None,
    tone: str | None = None,
) -> str:
    follow_up = choose_tone_variant(
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        tone=tone,
    )
    return (
        "⚠️ <b>Внимание</b>\n\n"
        "Сегодняшнего урока не будет.\n"
        "Причина: форс-мажор.\n\n"
        f"{follow_up}"
    )


BROADCAST_TEMPLATES = {
    "illness": build_illness_broadcast_text,
    "force_majeure": build_force_majeure_broadcast_text,
    "level_test": build_level_test_broadcast_text,
}


def _resolve_broadcast_text(
    kind: str | None,
    speech_style: str | None,
    fallback_text: str,
    *,
    info: dict | None = None,
    tone: str | None = None,
) -> str:
    if not kind:
        return fallback_text
    template = BROADCAST_TEMPLATES.get(kind)
    if callable(template):
        return template(speech_style, info=info, tone=tone)
    if isinstance(template, str) and template:
        return template
    return fallback_text


async def _enter_recipient_select(target, state: FSMContext, db: Database, broadcast_preview: str):
    students = await db.get_all_students()
    segments_enabled = await db.has_capability("segmented_broadcasts") if hasattr(db, "has_capability") else False
    if not students:
        msg = ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT
        back_kb = make_back_button_keyboard("◀️ К коммуникациям", "admin:cat:communication")
        if hasattr(target, 'message'):
            await target.message.edit_text(msg, reply_markup=back_kb)
            await target.answer()
        else:
            await target.answer(msg, reply_markup=back_kb)
        await state.clear()
        return

    cache = [
        {
            'telegram_id': student['telegram_id'],
            'full_name': student['full_name'],
            'speech_style': student.get('speech_style') or 'formal',
        }
        for student in students
    ]
    await state.update_data(
        recipient_ids=[],
        students_cache=cache,
        segment_mode_enabled=segments_enabled,
    )
    await state.set_state(AdminBroadcast.waiting_for_recipients)

    text = admin_broadcast_recipients_text(broadcast_preview, 0, len(cache))
    kb = make_recipient_select_keyboard(cache, set(), segments_enabled=segments_enabled)
    if hasattr(target, 'message'):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _show_broadcast_preview(target, state: FSMContext, broadcast_preview: str):
    await state.set_state(AdminBroadcast.waiting_for_text_confirm)
    text = build_broadcast_preview_text(broadcast_preview)
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=broadcast_preview_keyboard)
        await target.answer()
    else:
        await target.answer(text, reply_markup=broadcast_preview_keyboard)


@router.callback_query(lambda c: c.data == 'admin:broadcast')
async def admin_broadcast_start(callback_query: types.CallbackQuery, db: Database | None = None):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if db is not None and hasattr(db, "has_capability") and not await db.has_capability("segmented_broadcasts"):
        snapshot = await db.get_account_billing_snapshot()
        await callback_query.message.edit_text(
            build_paywall_text(capability_label("segmented_broadcasts"), snapshot, snapshot["product"]),
            reply_markup=make_paywall_keyboard(back_callback="admin:cat:communication", show_billing=True),
        )
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        ADMIN_BROADCAST_START_TEXT,
        reply_markup=broadcast_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('broadcast:'))
async def admin_broadcast_select(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    kind = callback_query.data.split(':', 1)[1]
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        admin_return_view="admin:cat:communication",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )

    if kind == 'custom':
        await state.set_state(AdminBroadcast.waiting_for_text)
        await state.update_data(broadcast_kind="custom")
        await callback_query.message.edit_text(
            ADMIN_BROADCAST_ENTER_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        await callback_query.answer()
        return

    template = BROADCAST_TEMPLATES.get(kind, '')
    ui_snapshot = await db.get_resolved_ui_config(db.require_account_id()) if hasattr(db, "get_resolved_ui_config") else {}
    ui_payload = resolve_ui_payload(ui_snapshot)
    broadcast_text = (
        template(
            None,
            info=build_teacher_info_from_ui(ui_payload),
            tone=ui_tone(ui_payload),
        )
        if callable(template)
        else template
    )
    await state.update_data(
        broadcast_kind=kind,
        broadcast_mode="text",
        broadcast_text=broadcast_text,
        broadcast_preview=broadcast_text,
        broadcast_source_chat_id=None,
        broadcast_source_message_id=None,
    )
    await _show_broadcast_preview(callback_query, state, broadcast_text)


@router.message(StateFilter(AdminBroadcast.waiting_for_text))
async def admin_broadcast_text_entered(message: types.Message, state: FSMContext):
    payload = extract_broadcast_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Отправьте текст, стикер, GIF или другое сообщение, которое нужно разослать.",
            reply_markup=cancel_fsm_keyboard,
        )
        return
    await state.update_data(
        broadcast_kind="custom",
        broadcast_mode=payload["mode"],
        broadcast_text=payload.get("text"),
        broadcast_preview=payload["preview"],
        broadcast_source_chat_id=payload.get("source_chat_id"),
        broadcast_source_message_id=payload.get("source_message_id"),
    )
    await _show_broadcast_preview(message, state, payload["preview"])


@router.callback_query(lambda c: c.data == 'bc_confirm', StateFilter(AdminBroadcast.waiting_for_text_confirm))
async def admin_broadcast_confirm_text(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    data = await state.get_data()
    await _enter_recipient_select(
        callback_query,
        state,
        db,
        data.get('broadcast_preview') or data.get('broadcast_text', ''),
    )


@router.callback_query(lambda c: c.data == 'bc_edit_text', StateFilter(AdminBroadcast.waiting_for_text_confirm))
async def admin_broadcast_edit_text(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminBroadcast.waiting_for_text)
    await callback_query.message.edit_text(
        ADMIN_BROADCAST_EDIT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'bc_back_preview', StateFilter(AdminBroadcast.waiting_for_recipients))
async def admin_broadcast_back_preview(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    await _show_broadcast_preview(
        callback_query,
        state,
        data.get("broadcast_preview") or data.get("broadcast_text", ""),
    )


@router.callback_query(
    lambda c: c.data.startswith('bc_toggle:'),
    StateFilter(AdminBroadcast.waiting_for_recipients),
)
async def bc_toggle_recipient(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(':')[1])
    data = await state.get_data()
    selected = set(data.get('recipient_ids', []))
    if student_id in selected:
        selected.discard(student_id)
    else:
        selected.add(student_id)
    await state.update_data(recipient_ids=list(selected))

    students = data.get('students_cache', [])
    broadcast_preview = data.get('broadcast_preview') or data.get('broadcast_text', '')
    text = admin_broadcast_recipients_text(broadcast_preview, len(selected), len(students))
    await callback_query.message.edit_text(
        text,
        reply_markup=make_recipient_select_keyboard(
            students,
            selected,
            segments_enabled=bool(data.get("segment_mode_enabled")),
        ),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data in ('bc_all', 'bc_none'),
    StateFilter(AdminBroadcast.waiting_for_recipients),
)
async def bc_select_all_none(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    students = data.get('students_cache', [])
    selected = {student['telegram_id'] for student in students} if callback_query.data == 'bc_all' else set()
    await state.update_data(recipient_ids=list(selected))

    broadcast_preview = data.get('broadcast_preview') or data.get('broadcast_text', '')
    text = admin_broadcast_recipients_text(broadcast_preview, len(selected), len(students))
    await callback_query.message.edit_text(
        text,
        reply_markup=make_recipient_select_keyboard(
            students,
            selected,
            segments_enabled=bool(data.get("segment_mode_enabled")),
        ),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('bc_segment:'),
    StateFilter(AdminBroadcast.waiting_for_recipients),
)
async def bc_segment_select(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    segment = callback_query.data.split(':', 1)[1]
    students = await db.get_broadcast_segment_students(segment)
    selected = {student["telegram_id"] for student in students}
    data = await state.get_data()
    cache = data.get("students_cache", [])
    await state.update_data(recipient_ids=list(selected))
    broadcast_preview = data.get('broadcast_preview') or data.get('broadcast_text', '')
    text = admin_broadcast_recipients_text(broadcast_preview, len(selected), len(cache))
    await callback_query.message.edit_text(
        text,
        reply_markup=make_recipient_select_keyboard(
            cache,
            selected,
            segments_enabled=bool(data.get("segment_mode_enabled")),
        ),
    )
    await callback_query.answer("Сегмент выбран.")


@router.callback_query(lambda c: c.data == 'noop')
async def noop_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'bc_send', StateFilter(AdminBroadcast.waiting_for_recipients))
async def bc_send(callback_query: types.CallbackQuery, state: FSMContext, db: Database | None = None):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    selected_ids = set(data.get('recipient_ids', []))
    if not selected_ids:
        await callback_query.answer("Выберите хотя бы одного получателя!", show_alert=True)
        return

    broadcast_mode = data.get("broadcast_mode", "text")
    broadcast_text = data.get('broadcast_text', '')
    broadcast_kind = data.get("broadcast_kind")
    source_chat_id = data.get("broadcast_source_chat_id")
    source_message_id = data.get("broadcast_source_message_id")
    students_cache = {
        student["telegram_id"]: student
        for student in data.get("students_cache", [])
    }
    reschedule_slots = (
        await build_reschedule_slot_payloads(db)
        if db is not None
        and broadcast_kind in {"illness", "force_majeure"}
        and hasattr(db, "has_capability")
        and await db.has_capability("smart_reschedule")
        else []
    )
    await state.clear()

    sent = 0
    for student_id in selected_ids:
        try:
            if broadcast_mode == "copy" and source_chat_id and source_message_id:
                await callback_query.bot.copy_message(
                    chat_id=student_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                    reply_markup=make_teacher_reply_keyboard("broadcast"),
                )
            else:
                student = students_cache.get(student_id)
                personalized_text = _resolve_broadcast_text(
                    broadcast_kind,
                    student.get("speech_style") if student else None,
                    broadcast_text,
                )
                reply_markup = make_teacher_reply_keyboard("broadcast")
                if reschedule_slots:
                    personalized_text += "\n\nВыберите удобный вариант переноса кнопкой ниже."
                    reply_markup = make_reschedule_offer_keyboard(reschedule_slots)
                await callback_query.bot.send_message(
                    student_id,
                    personalized_text,
                    reply_markup=reply_markup,
                )
            sent += 1
        except Exception:
            continue

    await callback_query.message.edit_text(
        build_broadcast_send_result_text(sent, len(selected_ids)),
        reply_markup=make_back_button_keyboard("◀️ К коммуникациям", "admin:cat:communication"),
    )
    await callback_query.answer()
