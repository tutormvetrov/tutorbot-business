from aiogram import types
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_back_button_keyboard,
    make_payment_delete_confirm_keyboard,
    make_payment_delete_keyboard,
    make_student_select_keyboard,
)
from states.registration import AdminAddPayment
from utils.db_api.postgresql import Database
from utils.domain_errors import BusinessRuleError
from utils.ui_text import (
    ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT,
    ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
    ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT,
    ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT,
    ADMIN_ADD_PAYMENT_START_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    build_admin_payments_text,
)

from handlers.users.admin_sections.common import get_message_origin, is_admin, q, restore_admin_view

router = Router()


def _return_view_from_source(source: str | None) -> str:
    return "admin:cat:education" if source == "education" else "admin:home"


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view and return_view.startswith("admin:student_card:") and student_id is not None:
        parts = return_view.split(":")
        if len(parts) == 4:
            return make_admin_context_keyboard(student_id, int(parts[3]))
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


async def _render_admin_payments(message: types.Message, db: Database, student_id: int, page: int | None = None):
    student = await db.get_user(student_id)
    name = q(student['full_name']) if student else str(student_id)
    payments = await db.get_student_payments(student_id, limit=20)
    balance = await db.get_student_lesson_balance(student_id)

    await message.edit_text(
        build_admin_payments_text(name, balance, payments),
        reply_markup=make_payment_delete_keyboard(student_id, payments, page=page),
    )


@router.callback_query(lambda c: c.data.startswith('admin:student_payments:'))
async def admin_student_payments(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    await _render_admin_payments(callback_query.message, db, student_id, page=page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('payment_delete_confirm:'))
async def admin_payment_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    _, student_id_str, payment_id_str = parts[:3]
    page = int(parts[3]) if len(parts) > 3 else None
    student_id = int(student_id_str)
    payment_id = int(payment_id_str)
    payment = await db.get_payment_by_id(payment_id)

    if not payment:
        await callback_query.message.edit_text(
            "⚠️ Оплата не найдена.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    date_str = payment['payment_date'].strftime('%d.%m.%Y') if payment.get('payment_date') else '—'
    await callback_query.message.edit_text(
        "🗑 <b>Удалить оплату?</b>\n\n"
        f"📅 Дата: <b>{date_str}</b>\n"
        f"💰 Сумма: <b>{int(payment['amount'])} ₽</b>\n"
        f"📚 Уроков: <b>{payment['lessons_count']}</b>\n"
        f"🎓 Остаток по платежу: <b>{payment['lessons_remaining']}</b>\n\n"
        "⚠️ Действие необратимо.",
        reply_markup=make_payment_delete_confirm_keyboard(student_id, payment_id, page=page),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('payment_delete:'))
async def admin_payment_delete(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    _, student_id_str, payment_id_str = parts[:3]
    page = int(parts[3]) if len(parts) > 3 else None
    student_id = int(student_id_str)
    payment_id = int(payment_id_str)
    payment = await db.get_payment_by_id(payment_id)

    if not payment:
        await callback_query.message.edit_text(
            "⚠️ Оплата уже удалена.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    try:
        await db.delete_payment(payment_id)
    except BusinessRuleError as exc:
        await callback_query.answer(str(exc), show_alert=True)
        return
    await _render_admin_payments(callback_query.message, db, student_id, page=page)
    await callback_query.answer("Оплата удалена.")


@router.callback_query(lambda c: c.data.startswith('admin:add_payment'))
async def admin_add_payment_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_REGISTERED_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard
        )
        await callback_query.answer()
        return

    await state.clear()
    await state.update_data(
        admin_return_view=_return_view_from_source(source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddPayment.waiting_for_payment_student)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_START_TEXT,
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_payment:'))
async def admin_add_payment_quick(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
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
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:'),
    StateFilter(AdminAddPayment.waiting_for_payment_student),
)
async def admin_payment_student_selected(callback_query: types.CallbackQuery, state: FSMContext):
    student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddPayment.waiting_for_payment_amount))
async def admin_payment_amount_entered(message: types.Message, state: FSMContext):
    try:
        amount = float((message.text or "").strip().replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.update_data(amount=amount)
    await state.set_state(AdminAddPayment.waiting_for_payment_count)
    await message.answer(
        ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminAddPayment.waiting_for_payment_count))
async def admin_payment_count_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        count = int((message.text or "").strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data['student_id']
    amount = data['amount']
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await db.add_payment(student_id, amount, count)

    student = await db.get_user(student_id)
    student_name = q(student['full_name']) if student else str(student_id)

    await state.clear()
    await restore_admin_view(message.bot, db, origin_chat_id, origin_message_id, return_view)
    await message.answer(
        f"✅ <b>Оплата добавлена</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"💰 Сумма: {int(amount)} ₽\n"
        f"🎓 Уроков: {count}\n\n"
        "Карточка и баланс уже обновлены.",
        reply_markup=_reply_markup_for_return_view(return_view, student_id),
    )
