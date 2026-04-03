from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from handlers.users.admin_sections.common import get_message_origin
from keyboards.inline import (
    admin_billing_keyboard,
    make_back_button_keyboard,
    make_billing_overrides_keyboard,
    make_group_detail_keyboard,
    make_groups_keyboard,
    make_invites_keyboard,
    make_paywall_keyboard,
    make_product_screen_keyboard,
    make_student_select_keyboard,
    product_hub_keyboard,
    support_keyboard,
)
from states.registration import AdminGroups
from utils.capabilities import capability_label
from utils.db_api.postgresql import Database
from utils.product_ui import (
    build_analytics_text,
    build_billing_admin_text,
    build_group_detail_text,
    build_groups_text,
    build_included_text,
    build_invites_text,
    build_paywall_text,
    build_plans_text,
    build_product_hub_text,
    build_subscription_text,
    build_support_text,
    build_try_or_extend_text,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


async def _show_paywall(
    message: types.Message,
    db: Database,
    capability: str,
    back_callback: str,
    show_billing: bool = False,
):
    snapshot = await db.get_account_billing_snapshot()
    product = snapshot["product"]
    await message.edit_text(
        build_paywall_text(capability_label(capability), snapshot, product),
        reply_markup=make_paywall_keyboard(back_callback=back_callback, show_billing=show_billing),
    )


@router.callback_query(lambda c: c.data == "product:hub")
async def product_hub(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_product_hub_text(snapshot, snapshot["product"]),
        reply_markup=product_hub_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:plans")
async def product_plans(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_plans_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_is_admin(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:included")
async def product_included(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_included_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_is_admin(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:subscription")
async def product_subscription(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_subscription_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_is_admin(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:trial")
async def product_trial(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_try_or_extend_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_is_admin(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:billing")
async def admin_billing(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_billing_admin_text(snapshot, snapshot["product"]),
        reply_markup=admin_billing_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:billing:activate:"))
async def admin_billing_activate(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, plan_code, days_str = callback_query.data.split(":")
    await db.activate_paid_subscription(plan_code, int(days_str), activated_by=callback_query.from_user.id)
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_billing_admin_text(snapshot, snapshot["product"]),
        reply_markup=admin_billing_keyboard,
    )
    await callback_query.answer("Подписка обновлена.")


@router.callback_query(lambda c: c.data.startswith("admin:billing:trial:"))
async def admin_billing_trial(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    days = int(callback_query.data.split(":")[3])
    await db.extend_trial(days, activated_by=callback_query.from_user.id)
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_billing_admin_text(snapshot, snapshot["product"]),
        reply_markup=admin_billing_keyboard,
    )
    await callback_query.answer("Trial продлён.")


@router.callback_query(lambda c: c.data == "admin:billing:disable_trial")
async def admin_billing_disable_trial(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await db.disable_trial(activated_by=callback_query.from_user.id)
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_billing_admin_text(snapshot, snapshot["product"]),
        reply_markup=admin_billing_keyboard,
    )
    await callback_query.answer("Trial отключён.")


@router.callback_query(lambda c: c.data == "admin:billing:overrides")
async def admin_billing_overrides(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_subscription_text(snapshot, snapshot["product"]),
        reply_markup=make_billing_overrides_keyboard(set(snapshot["overrides"].keys())),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:billing:override:"))
async def admin_billing_override_toggle(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    capability = callback_query.data.split(":", 3)[3]
    enabled = await db.toggle_feature_override(capability, updated_by=callback_query.from_user.id)
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_subscription_text(snapshot, snapshot["product"]),
        reply_markup=make_billing_overrides_keyboard(set(snapshot["overrides"].keys())),
    )
    await callback_query.answer("Override включён." if enabled else "Override снят.")


@router.callback_query(lambda c: c.data == "admin:invites")
async def admin_invites(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(invites),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:invite:create:"))
async def admin_invite_create(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    role = callback_query.data.split(":")[3]
    await db.create_account_invite(role, created_by=callback_query.from_user.id, label=f"{role}-seat")
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(invites),
    )
    await callback_query.answer("Инвайт создан.")


@router.callback_query(lambda c: c.data.startswith("admin:invite:revoke:"))
async def admin_invite_revoke(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    invite_id = int(callback_query.data.split(":")[3])
    await db.revoke_account_invite(invite_id)
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(invites),
    )
    await callback_query.answer("Инвайт отозван.")


@router.callback_query(lambda c: c.data == "admin:support")
async def admin_support(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    support_snapshot = await db.get_support_snapshot()
    product = support_snapshot["billing"]["product"]
    await callback_query.message.edit_text(
        build_support_text(support_snapshot, product),
        reply_markup=support_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:analytics")
async def admin_analytics(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("analytics_lite"):
        await _show_paywall(
            callback_query.message,
            db,
            "analytics_lite",
            back_callback="admin:cat:service",
            show_billing=True,
        )
        await callback_query.answer()
        return
    snapshot = await db.get_account_billing_snapshot()
    analytics = await db.get_account_analytics_snapshot()
    await callback_query.message.edit_text(
        build_analytics_text(snapshot, dict(analytics or {}), snapshot["product"]),
        reply_markup=make_back_button_keyboard("◀️ К сервису", "admin:cat:service"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:groups")
async def admin_groups(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("groups"):
        await _show_paywall(
            callback_query.message,
            db,
            "groups",
            back_callback="admin:cat:students",
            show_billing=True,
        )
        await callback_query.answer()
        return
    groups = await db.get_groups_overview()
    await callback_query.message.edit_text(
        build_groups_text(groups),
        reply_markup=make_groups_keyboard(groups),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:groups:create")
async def admin_groups_create_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("groups"):
        await _show_paywall(
            callback_query.message,
            db,
            "groups",
            back_callback="admin:cat:students",
            show_billing=True,
        )
        await callback_query.answer()
        return
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.set_state(AdminGroups.waiting_for_name)
    await state.update_data(
        admin_return_view="admin:groups",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        "👥 <b>Новая группа</b>\n\nВведите название группы одним сообщением.",
        reply_markup=make_back_button_keyboard("◀️ К группам", "admin:groups"),
    )
    await callback_query.answer()


@router.message(StateFilter(AdminGroups.waiting_for_name))
async def admin_groups_create_name(message: types.Message, state: FSMContext, db: Database):
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ Название группы не может быть пустым.")
        return
    group_id = await db.create_group(name)
    await state.clear()
    group = await db.get_group(group_id)
    members = await db.get_group_members(group_id)
    await message.answer(
        build_group_detail_text(group, members),
        reply_markup=make_group_detail_keyboard(group_id),
    )


@router.callback_query(lambda c: c.data.startswith("admin:group:view:"))
async def admin_group_view(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    group_id = int(callback_query.data.split(":")[3])
    group = await db.get_group(group_id)
    if not group:
        await callback_query.message.edit_text(
            "⚠️ Группа не найдена.",
            reply_markup=make_back_button_keyboard("◀️ К группам", "admin:groups"),
        )
        await callback_query.answer()
        return
    members = await db.get_group_members(group_id)
    await callback_query.message.edit_text(
        build_group_detail_text(group, members),
        reply_markup=make_group_detail_keyboard(group_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:group:add_student:"))
async def admin_group_add_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    group_id = int(callback_query.data.split(":")[3])
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            "⚠️ Нет активных учеников для добавления.",
            reply_markup=make_back_button_keyboard("◀️ К группам", "admin:groups"),
        )
        await callback_query.answer()
        return
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.set_state(AdminGroups.waiting_for_student)
    await state.update_data(
        group_id=group_id,
        admin_return_view=f"admin:group:view:{group_id}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        "👥 <b>Добавить ученика в группу</b>\n\nВыберите ученика:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith("select_student:"),
    StateFilter(AdminGroups.waiting_for_student),
)
async def admin_group_add_student_confirm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    data = await state.get_data()
    group_id = data.get("group_id")
    student_id = int(callback_query.data.split(":")[1])
    await db.add_student_to_group(group_id, student_id)
    await state.clear()
    group = await db.get_group(group_id)
    members = await db.get_group_members(group_id)
    await callback_query.message.edit_text(
        build_group_detail_text(group, members),
        reply_markup=make_group_detail_keyboard(group_id),
    )
    await callback_query.answer("Ученик добавлен.")


@router.callback_query(lambda c: c.data.startswith("admin:group:delete:"))
async def admin_group_delete(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    group_id = int(callback_query.data.split(":")[3])
    await db.delete_group(group_id)
    groups = await db.get_groups_overview()
    await callback_query.message.edit_text(
        build_groups_text(groups),
        reply_markup=make_groups_keyboard(groups),
    )
    await callback_query.answer("Группа архивирована.")
