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
    make_product_hub_keyboard,
    make_product_screen_keyboard,
    make_student_select_keyboard,
    make_team_keyboard,
    make_ui_history_keyboard,
    make_ui_menu_section_keyboard,
    make_ui_menu_sections_keyboard,
    make_ui_preview_keyboard,
    make_ui_preview_menu_keyboard,
    make_ui_section_keyboard,
    make_ui_tone_keyboard,
    owner_setup_keyboard,
    support_keyboard,
    ui_constructor_keyboard,
)
from states.registration import AdminGroups, AdminUiEditor
from utils.account_ui import (
    UI_MENU_SECTION_LABELS,
    build_ui_update,
    find_menu_entry,
    get_menu_entries,
    make_custom_menu_item_id,
    replace_menu_section,
    resolve_ui_payload,
    validate_custom_menu_url,
)
from utils.capabilities import capability_label
from utils.db_api.postgresql import Database
from utils.domain_errors import BusinessRuleError
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
    build_team_text,
    build_try_or_extend_text,
    build_owner_setup_text,
    build_ui_branding_text,
    build_ui_contacts_text,
    build_ui_copy_text,
    build_ui_history_text,
    build_ui_hub_text,
    build_ui_menu_section_text,
    build_ui_menu_sections_text,
    build_ui_preview_text,
    build_ui_requisites_text,
)
from utils.workspace import (
    has_workspace_admin_access,
    has_workspace_assistant_invite_access,
    has_workspace_billing_access,
    has_workspace_manager_invite_access,
    has_workspace_staff_access,
    has_workspace_support_access,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return has_workspace_admin_access(user_id)


def _can_manage_billing(user_id: int) -> bool:
    return has_workspace_billing_access(user_id)


def _can_manage_invites(user_id: int) -> bool:
    return has_workspace_assistant_invite_access(user_id)


def _can_view_support(user_id: int) -> bool:
    return has_workspace_support_access(user_id)


def _can_view_team(user_id: int) -> bool:
    return has_workspace_staff_access(user_id)


def _can_manage_ui(user_id: int) -> bool:
    return has_workspace_admin_access(user_id)


UI_SECTION_FIELDS = {
    "branding": [
        ("display_name", "✏️ Название аккаунта"),
        ("tone", "🎨 Тональность"),
    ],
    "copy": [
        ("start_intro", "✏️ Текст старта"),
        ("help_intro", "✏️ Текст справки"),
        ("contacts_intro", "✏️ Вступление в контактах"),
        ("requisites_footer", "✏️ Подсказка в реквизитах"),
        ("post_registration_intro", "✏️ Текст после регистрации"),
    ],
    "contacts": [
        ("phone", "✏️ Телефон"),
        ("telegram", "✏️ Telegram"),
        ("discord", "✏️ Discord"),
        ("address", "✏️ Адрес"),
        ("booking_url", "✏️ Ссылка на запись"),
        ("calendar_url", "✏️ Ссылка на расписание"),
        ("project_site_url", "✏️ Сайт"),
        ("level_test_url", "✏️ Тест уровня"),
        ("review_url", "✏️ Отзывы"),
        ("vk_call", "✏️ VK Звонок"),
        ("google_meet", "✏️ Google Meet"),
    ],
    "requisites": [
        ("rates", "✏️ Ставки"),
        ("card", "✏️ Карта"),
        ("sbp", "✏️ СБП"),
        ("sbp_banks", "✏️ Банки СБП"),
        ("usdt_trc20", "✏️ USDT TRC-20"),
    ],
}

def _btn(text: str, callback_data: str):
    return types.InlineKeyboardButton(text=text, callback_data=callback_data)


admin_billing_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("Start · 30 дней", "admin:billing:activate:start:30"), _btn("Practice · 30 дней", "admin:billing:activate:practice:30")],
    [_btn("Studio · 30 дней", "admin:billing:activate:studio:30"), _btn("Practice · 90 дней", "admin:billing:activate:practice:90")],
    [_btn("➕ Пробный +7 дней", "admin:billing:trial:7"), _btn("➕ Пробный +14 дней", "admin:billing:trial:14")],
    [_btn("⛔ Завершить пробный", "admin:billing:disable_trial")],
    [_btn("🧩 Доп. функции", "admin:billing:overrides")],
    [_btn("◀️ К аккаунту", "admin:cat:account")],
])

support_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👥 Команда", "admin:team"), _btn("🔗 Инвайты", "admin:invites")],
    [_btn("🧾 Тариф", "admin:billing"), _btn("🏢 Аккаунт", "workspace:selector")],
    [_btn("◀️ К аккаунту", "admin:cat:account")],
])

ui_constructor_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎨 Оформление", "admin:ui:branding"), _btn("🧾 Тексты", "admin:ui:copy")],
    [_btn("📞 Контакты", "admin:ui:contacts"), _btn("💳 Реквизиты", "admin:ui:requisites")],
    [_btn("📚 Меню", "admin:ui:menu"), _btn("👁 Предпросмотр", "admin:ui:preview")],
    [_btn("🚀 Опубликовать", "admin:ui:publish"), _btn("🕘 История", "admin:ui:history")],
    [_btn("◀️ К системе", "admin:cat:system")],
])

owner_setup_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎨 Оформление", "admin:ui"), _btn("📞 Контакты", "admin:ui:contacts")],
    [_btn("💳 Реквизиты", "admin:ui:requisites"), _btn("👤 Добавить ученика", "admin:add_student")],
    [_btn("➕ Добавить занятие", "admin:add_lesson:education"), _btn("🔄 Calendar", "admin:sync:system")],
    [_btn("🧾 Подписка и тариф", "admin:billing"), _btn("💼 Продукт", "product:hub")],
    [_btn("◀️ К системе", "admin:cat:system")],
])


def _section_back_callback(section: str) -> str:
    if section == "menu":
        return "admin:ui:menu"
    return f"admin:ui:{section}"


def _parse_multiline_rates(raw: str) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _normalize_field_value(section: str, field: str, raw: str):
    value = (raw or "").strip()
    if value in {"-", "—", "очистить", "clear"}:
        return [] if field == "rates" else ""
    if field == "rates":
        return _parse_multiline_rates(value)
    return value


async def _get_ui_snapshot(db: Database, *, draft: bool = False) -> dict:
    account_id = db.require_account_id()
    if draft and hasattr(db, "get_ui_draft"):
        return await db.get_ui_draft(account_id)
    if hasattr(db, "get_resolved_ui_config"):
        return await db.get_resolved_ui_config(account_id)
    return {}


async def _render_ui_hub(message: types.Message, db: Database):
    snapshot = await _get_ui_snapshot(db, draft=True)
    await message.edit_text(
        build_ui_hub_text(snapshot),
        reply_markup=ui_constructor_keyboard,
    )


async def _render_ui_section(message: types.Message, db: Database, section: str):
    snapshot = await _get_ui_snapshot(db, draft=True)
    if section == "branding":
        text = build_ui_branding_text(snapshot)
    elif section == "copy":
        text = build_ui_copy_text(snapshot)
    elif section == "contacts":
        text = build_ui_contacts_text(snapshot)
    else:
        text = build_ui_requisites_text(snapshot)
    keyboard = make_ui_section_keyboard(section, UI_SECTION_FIELDS[section], back_callback="admin:ui")
    await message.edit_text(text, reply_markup=keyboard)


async def _render_ui_menu(message: types.Message, db: Database):
    snapshot = await _get_ui_snapshot(db, draft=True)
    await message.edit_text(
        build_ui_menu_sections_text(snapshot),
        reply_markup=make_ui_menu_sections_keyboard(),
    )


async def _render_ui_menu_section(message: types.Message, db: Database, section: str):
    snapshot = await _get_ui_snapshot(db, draft=True)
    ui_payload = resolve_ui_payload(snapshot)
    await message.edit_text(
        build_ui_menu_section_text(snapshot, section),
        reply_markup=make_ui_menu_section_keyboard(section, get_menu_entries(ui_payload, section)),
    )


def _menu_custom_button_prompt(section: str) -> str:
    label = UI_MENU_SECTION_LABELS.get(section, section)
    return (
        f"🔗 <b>Новая кнопка: {label}</b>\n\n"
        "Отправьте строку в формате:\n"
        "<code>Название | https://example.com</code>\n\n"
        "Поддерживаются обычные ссылки и Telegram-ссылки. Чтобы отменить ввод, нажмите кнопку ниже."
    )


def _field_prompt(section: str, field: str) -> str:
    prompts = {
        ("branding", "display_name"): "Введите новое название аккаунта одним сообщением.",
        ("copy", "start_intro"): "Введите короткий текст для приветствия на старте.",
        ("copy", "help_intro"): "Введите короткий вводный текст для экрана справки.",
        ("copy", "contacts_intro"): "Введите вступление для экрана контактов.",
        ("copy", "requisites_footer"): "Введите подсказку для экрана реквизитов.",
        ("copy", "post_registration_intro"): "Введите короткий текст после завершения регистрации.",
        ("requisites", "rates"): "Введите ставки, каждая с новой строки.\nНапример:\n<code>0 рублей / 60 минут\n0 рублей / 90 минут</code>",
    }
    default = "Введите новое значение одним сообщением.\nЧтобы очистить поле, отправьте <code>-</code>."
    return prompts.get((section, field), default)


async def _start_ui_edit(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    *,
    section: str,
    field: str,
    title: str,
):
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.set_state(AdminUiEditor.waiting_for_value)
    await state.update_data(
        ui_section=section,
        ui_field=field,
        admin_return_view=_section_back_callback(section),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        f"{title}\n\n{_field_prompt(section, field)}",
        reply_markup=make_back_button_keyboard("◀️ Назад", _section_back_callback(section)),
    )


async def _edit_ui_origin(bot, state_data: dict, text: str, reply_markup):
    chat_id = state_data.get("admin_origin_chat_id")
    message_id = state_data.get("admin_origin_message_id")
    if not chat_id or not message_id:
        return False
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )
    return True


async def _render_ui_section_via_origin(
    bot,
    state_data: dict,
    snapshot: dict,
    *,
    section: str,
    menu_section: str | None = None,
):
    if section == "menu" and menu_section:
        return await _edit_ui_origin(
            bot,
            state_data,
            build_ui_menu_section_text(snapshot, menu_section),
            make_ui_menu_section_keyboard(menu_section, get_menu_entries(resolve_ui_payload(snapshot), menu_section)),
        )
    render_map = {
        "branding": build_ui_branding_text,
        "copy": build_ui_copy_text,
        "contacts": build_ui_contacts_text,
        "requisites": build_ui_requisites_text,
    }
    return await _edit_ui_origin(
        bot,
        state_data,
        render_map[section](snapshot),
        make_ui_section_keyboard(section, UI_SECTION_FIELDS[section], back_callback="admin:ui"),
    )

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
        reply_markup=make_product_hub_keyboard(
            show_team=_can_view_team(callback_query.from_user.id),
            show_setup=_can_manage_ui(callback_query.from_user.id),
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:plans")
async def product_plans(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_plans_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_can_manage_billing(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:included")
async def product_included(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_included_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_can_manage_billing(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:subscription")
async def product_subscription(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_subscription_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_can_manage_billing(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "product:trial")
async def product_trial(callback_query: types.CallbackQuery, db: Database):
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_try_or_extend_text(snapshot, snapshot["product"]),
        reply_markup=make_product_screen_keyboard(show_billing=_can_manage_billing(callback_query.from_user.id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data in {"product:team", "admin:team"})
async def product_team(callback_query: types.CallbackQuery, db: Database):
    if not _can_view_team(callback_query.from_user.id):
        await callback_query.answer()
        return
    account = await db.get_account()
    team_members = await db.get_account_team_members()
    account_user = await db.get_account_user(callback_query.from_user.id, account["id"]) if account else None
    is_admin_view = callback_query.data == "admin:team"
    await callback_query.message.edit_text(
        build_team_text(dict(account or {}), [dict(item) for item in team_members], (account_user or {}).get("role")),
        reply_markup=make_team_keyboard(
            back_callback="admin:cat:account" if is_admin_view else "product:hub",
            allow_manager_invite=has_workspace_manager_invite_access(callback_query.from_user.id),
            allow_assistant_invite=has_workspace_assistant_invite_access(callback_query.from_user.id),
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:billing")
async def admin_billing(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_billing(callback_query.from_user.id):
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
    if not _can_manage_billing(callback_query.from_user.id):
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
    if not _can_manage_billing(callback_query.from_user.id):
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
    if not _can_manage_billing(callback_query.from_user.id):
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
    if not _can_manage_billing(callback_query.from_user.id):
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
    if not _can_manage_billing(callback_query.from_user.id):
        await callback_query.answer()
        return
    capability = callback_query.data.split(":", 3)[3]
    enabled = await db.toggle_feature_override(capability, updated_by=callback_query.from_user.id)
    snapshot = await db.get_account_billing_snapshot()
    await callback_query.message.edit_text(
        build_subscription_text(snapshot, snapshot["product"]),
        reply_markup=make_billing_overrides_keyboard(set(snapshot["overrides"].keys())),
    )
    await callback_query.answer("Функция включена." if enabled else "Функция отключена.")


@router.callback_query(lambda c: c.data == "admin:invites")
async def admin_invites(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_invites(callback_query.from_user.id):
        await callback_query.answer()
        return
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(
            [dict(item) for item in invites],
            allow_manager_invite=has_workspace_manager_invite_access(callback_query.from_user.id),
            allow_assistant_invite=has_workspace_assistant_invite_access(callback_query.from_user.id),
            back_callback="admin:cat:account",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:invite:create:"))
async def admin_invite_create(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_invites(callback_query.from_user.id):
        await callback_query.answer()
        return
    role = callback_query.data.split(":")[3]
    if role == "manager" and not has_workspace_manager_invite_access(callback_query.from_user.id):
        await callback_query.answer("Только владелец может приглашать менеджера.", show_alert=True)
        return
    if role == "assistant" and not has_workspace_assistant_invite_access(callback_query.from_user.id):
        await callback_query.answer("Недостаточно прав для инвайта ассистента.", show_alert=True)
        return
    try:
        await db.create_account_invite(role, created_by=callback_query.from_user.id, label=f"{role}-seat")
    except BusinessRuleError as exc:
        await callback_query.answer(str(exc), show_alert=True)
        return
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(
            [dict(item) for item in invites],
            allow_manager_invite=has_workspace_manager_invite_access(callback_query.from_user.id),
            allow_assistant_invite=has_workspace_assistant_invite_access(callback_query.from_user.id),
            back_callback="admin:cat:account",
        ),
    )
    await callback_query.answer("Инвайт создан.")


@router.callback_query(lambda c: c.data.startswith("admin:invite:revoke:"))
async def admin_invite_revoke(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_invites(callback_query.from_user.id):
        await callback_query.answer()
        return
    invite_id = int(callback_query.data.split(":")[3])
    await db.revoke_account_invite(invite_id)
    account = await db.get_account()
    invites = await db.get_active_account_invites()
    bot_username = (await callback_query.bot.get_me()).username
    await callback_query.message.edit_text(
        build_invites_text(dict(account or {}), [dict(item) for item in invites], bot_username=bot_username),
        reply_markup=make_invites_keyboard(
            [dict(item) for item in invites],
            allow_manager_invite=has_workspace_manager_invite_access(callback_query.from_user.id),
            allow_assistant_invite=has_workspace_assistant_invite_access(callback_query.from_user.id),
            back_callback="admin:cat:account",
        ),
    )
    await callback_query.answer("Инвайт отозван.")


@router.callback_query(lambda c: c.data == "admin:support")
async def admin_support(callback_query: types.CallbackQuery, db: Database):
    if not _can_view_support(callback_query.from_user.id):
        await callback_query.answer()
        return
    support_snapshot = await db.get_support_snapshot(operator_telegram_id=callback_query.from_user.id)
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
            back_callback="admin:cat:account",
            show_billing=_can_manage_billing(callback_query.from_user.id),
        )
        await callback_query.answer()
        return
    snapshot = await db.get_account_billing_snapshot()
    analytics = await db.get_account_analytics_snapshot()
    await callback_query.message.edit_text(
        build_analytics_text(snapshot, dict(analytics or {}), snapshot["product"]),
        reply_markup=make_back_button_keyboard("◀️ К аккаунту", "admin:cat:account"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:ui")
async def admin_ui_hub(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_ui_hub(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:setup")
async def owner_setup(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    ui_snapshot = await _get_ui_snapshot(db, draft=True)
    analytics = await db.get_account_analytics_snapshot()
    billing_snapshot = await db.get_account_billing_snapshot()
    calendar_connected = bool((config.GOOGLE_CALENDAR_ID or "").strip())
    await callback_query.message.edit_text(
        build_owner_setup_text(ui_snapshot, dict(analytics or {}), billing_snapshot, calendar_connected=calendar_connected),
        reply_markup=owner_setup_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data in {"admin:ui:branding", "admin:ui:copy", "admin:ui:contacts", "admin:ui:requisites"})
async def admin_ui_section(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    section = callback_query.data.split(":")[2]
    await _render_ui_section(callback_query.message, db, section)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:ui:menu")
async def admin_ui_menu(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_ui_menu(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:section:"))
async def admin_ui_menu_section(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    section = callback_query.data.split(":", 4)[4]
    await _render_ui_menu_section(callback_query.message, db, section)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:edit:"))
async def admin_ui_edit_field(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, section, field = callback_query.data.split(":", 4)
    if field == "tone":
        snapshot = await _get_ui_snapshot(db, draft=True)
        tone = resolve_ui_payload(snapshot).get("branding", {}).get("tone", "warm")
        await callback_query.message.edit_text(
            build_ui_branding_text(snapshot),
            reply_markup=make_ui_tone_keyboard(tone),
        )
        await callback_query.answer()
        return
    title = {
        "branding": "🎨 <b>Редактирование оформления</b>",
        "copy": "🧾 <b>Редактирование клиентского текста</b>",
        "contacts": "📞 <b>Редактирование контакта</b>",
        "requisites": "💳 <b>Редактирование реквизита</b>",
    }.get(section, "✏️ <b>Редактирование поля</b>")
    await _start_ui_edit(callback_query, state, section=section, field=field, title=title)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:tone:"))
async def admin_ui_set_tone(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    tone = callback_query.data.split(":")[3]
    await db.save_ui_draft(
        db.require_account_id(),
        build_ui_update("branding", "tone", tone),
        updated_by=callback_query.from_user.id,
    )
    await _render_ui_section(callback_query.message, db, "branding")
    await callback_query.answer("Тональность обновлена.")


@router.message(StateFilter(AdminUiEditor.waiting_for_value))
async def admin_ui_save_field(message: types.Message, state: FSMContext, db: Database):
    data = await state.get_data()
    section = data.get("ui_section")
    field = data.get("ui_field")
    mode = data.get("ui_mode")
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("⚠️ Значение не должно быть пустым.")
        return

    if mode == "menu_add":
        menu_section = data.get("ui_menu_section")
        if "|" not in raw:
            await message.answer("⚠️ Используйте формат: <code>Название | https://example.com</code>")
            return
        label, url = [part.strip() for part in raw.split("|", 1)]
        try:
            normalized_url, kind = validate_custom_menu_url(url)
        except ValueError as exc:
            await message.answer(f"⚠️ {exc}")
            return
        snapshot = await _get_ui_snapshot(db, draft=True)
        ui_payload = resolve_ui_payload(snapshot)
        entries = get_menu_entries(ui_payload, menu_section)
        entries.append({
            "id": make_custom_menu_item_id(entries),
            "label": label,
            "value": normalized_url,
            "kind": kind,
            "enabled": True,
            "order": len(entries) + 1,
        })
        updated_payload = replace_menu_section(ui_payload, menu_section, entries)
        await db.save_ui_draft(
            db.require_account_id(),
            {"menu": {menu_section: updated_payload["menu"][menu_section]}},
            updated_by=message.from_user.id,
        )
        snapshot = await _get_ui_snapshot(db, draft=True)
        await state.clear()
        await _render_ui_section_via_origin(message.bot, data, snapshot, section="menu", menu_section=menu_section)
        await message.answer("✅ Кнопка добавлена.")
        return

    if mode == "menu_rename":
        menu_section = data.get("ui_menu_section")
        item_id = data.get("ui_menu_item_id")
        snapshot = await _get_ui_snapshot(db, draft=True)
        ui_payload = resolve_ui_payload(snapshot)
        entries = get_menu_entries(ui_payload, menu_section)
        for item in entries:
            if str(item.get("id")) == str(item_id):
                item["label"] = raw
                break
        updated_payload = replace_menu_section(ui_payload, menu_section, entries)
        await db.save_ui_draft(
            db.require_account_id(),
            {"menu": {menu_section: updated_payload["menu"][menu_section]}},
            updated_by=message.from_user.id,
        )
        snapshot = await _get_ui_snapshot(db, draft=True)
        await state.clear()
        await _render_ui_section_via_origin(message.bot, data, snapshot, section="menu", menu_section=menu_section)
        await message.answer("✅ Название кнопки обновлено.")
        return

    value = _normalize_field_value(section, field, raw)
    await db.save_ui_draft(
        db.require_account_id(),
        build_ui_update(section, field, value),
        updated_by=message.from_user.id,
    )
    section_snapshot = await _get_ui_snapshot(db, draft=True)
    await state.clear()
    await _render_ui_section_via_origin(message.bot, data, section_snapshot, section=section)
    await message.answer("✅ Черновик обновлён.")


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:toggle:"))
async def admin_ui_menu_toggle(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, _, section, item_id = callback_query.data.split(":", 5)
    snapshot = await _get_ui_snapshot(db, draft=True)
    ui_payload = resolve_ui_payload(snapshot)
    entries = get_menu_entries(ui_payload, section)
    for item in entries:
        if str(item.get("id")) == item_id:
            item["enabled"] = not item.get("enabled", True)
            break
    updated_payload = replace_menu_section(ui_payload, section, entries)
    await db.save_ui_draft(
        db.require_account_id(),
        {"menu": {section: updated_payload["menu"][section]}},
        updated_by=callback_query.from_user.id,
    )
    await _render_ui_menu_section(callback_query.message, db, section)
    await callback_query.answer("Состояние кнопки обновлено.")


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:move:"))
async def admin_ui_menu_move(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, _, section, item_id, direction = callback_query.data.split(":", 6)
    snapshot = await _get_ui_snapshot(db, draft=True)
    ui_payload = resolve_ui_payload(snapshot)
    entries = get_menu_entries(ui_payload, section)
    index = next((i for i, item in enumerate(entries) if str(item.get("id")) == item_id), None)
    if index is None:
        await callback_query.answer("Кнопка не найдена.", show_alert=True)
        return
    if direction == "up" and index > 0:
        entries[index - 1], entries[index] = entries[index], entries[index - 1]
    elif direction == "down" and index < len(entries) - 1:
        entries[index + 1], entries[index] = entries[index], entries[index + 1]
    updated_payload = replace_menu_section(ui_payload, section, entries)
    await db.save_ui_draft(
        db.require_account_id(),
        {"menu": {section: updated_payload["menu"][section]}},
        updated_by=callback_query.from_user.id,
    )
    await _render_ui_menu_section(callback_query.message, db, section)
    await callback_query.answer("Порядок обновлён.")


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:add:"))
async def admin_ui_menu_add(callback_query: types.CallbackQuery, state: FSMContext):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    section = callback_query.data.split(":")[4]
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.set_state(AdminUiEditor.waiting_for_value)
    await state.update_data(
        ui_mode="menu_add",
        ui_menu_section=section,
        admin_return_view=f"admin:ui:menu:section:{section}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        _menu_custom_button_prompt(section),
        reply_markup=make_back_button_keyboard("◀️ Назад", f"admin:ui:menu:section:{section}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:rename:"))
async def admin_ui_menu_rename(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, _, section, item_id = callback_query.data.split(":", 5)
    item = find_menu_entry(resolve_ui_payload(await _get_ui_snapshot(db, draft=True)), section, item_id)
    title = f"✏️ <b>Переименование кнопки</b>\n\nСейчас: <b>{item.get('label', item_id) if item else item_id}</b>"
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.set_state(AdminUiEditor.waiting_for_value)
    await state.update_data(
        ui_mode="menu_rename",
        ui_menu_section=section,
        ui_menu_item_id=item_id,
        admin_return_view=f"admin:ui:menu:section:{section}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        f"{title}\n\nВведите новое название одним сообщением.",
        reply_markup=make_back_button_keyboard("◀️ Назад", f"admin:ui:menu:section:{section}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:menu:delete:"))
async def admin_ui_menu_delete(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, _, _, section, item_id = callback_query.data.split(":", 5)
    snapshot = await _get_ui_snapshot(db, draft=True)
    ui_payload = resolve_ui_payload(snapshot)
    entries = [item for item in get_menu_entries(ui_payload, section) if str(item.get("id")) != item_id]
    updated_payload = replace_menu_section(ui_payload, section, entries)
    await db.save_ui_draft(
        db.require_account_id(),
        {"menu": {section: updated_payload["menu"][section]}},
        updated_by=callback_query.from_user.id,
    )
    await _render_ui_menu_section(callback_query.message, db, section)
    await callback_query.answer("Кнопка удалена.")


@router.callback_query(lambda c: c.data == "admin:ui:preview")
async def admin_ui_preview_roles(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "👁 <b>Предпросмотр</b>\n\nВыберите роль ниже. Бот покажет черновое меню и стартовый экран именно так, как их увидит пользователь после публикации.",
        reply_markup=make_ui_preview_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:preview:"))
async def admin_ui_preview_role(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    role = callback_query.data.split(":")[3]
    snapshot = await _get_ui_snapshot(db, draft=True)
    await callback_query.message.edit_text(
        build_ui_preview_text(snapshot, role),
        reply_markup=make_ui_preview_menu_keyboard(resolve_ui_payload(snapshot), role),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:ui:publish")
async def admin_ui_publish(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    await db.publish_ui_draft(db.require_account_id(), published_by=callback_query.from_user.id)
    await _render_ui_hub(callback_query.message, db)
    await callback_query.answer("Черновик опубликован.")


@router.callback_query(lambda c: c.data == "admin:ui:history")
async def admin_ui_history(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    snapshot = await _get_ui_snapshot(db, draft=True)
    versions = await db.list_ui_versions(db.require_account_id())
    await callback_query.message.edit_text(
        build_ui_history_text(snapshot, versions),
        reply_markup=make_ui_history_keyboard(versions),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:ui:rollback:"))
async def admin_ui_rollback(callback_query: types.CallbackQuery, db: Database):
    if not _can_manage_ui(callback_query.from_user.id):
        await callback_query.answer()
        return
    version = int(callback_query.data.split(":")[3])
    await db.rollback_ui_version(db.require_account_id(), version, actor_id=callback_query.from_user.id)
    snapshot = await _get_ui_snapshot(db, draft=True)
    versions = await db.list_ui_versions(db.require_account_id())
    await callback_query.message.edit_text(
        build_ui_history_text(snapshot, versions),
        reply_markup=make_ui_history_keyboard(versions),
    )
    await callback_query.answer("Откат выполнен.")


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
            show_billing=_can_manage_billing(callback_query.from_user.id),
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
            show_billing=_can_manage_billing(callback_query.from_user.id),
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
    try:
        group_id = await db.create_group(name)
    except BusinessRuleError as exc:
        await state.clear()
        await message.answer(
            f"⚠️ {str(exc)}",
            reply_markup=make_back_button_keyboard("◀️ К группам", "admin:groups"),
        )
        return
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
