import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from data import config
from keyboards.inline import (
    back_to_menu_keyboard,
    get_main_menu_keyboard,
    make_workspace_selector_keyboard,
    profile_keyboard,
    parent_profile_keyboard,
)
from utils.account_ui import resolve_ui_payload, ui_copy_text, ui_display_name, ui_tone
from utils.db_api.postgresql import Database
from utils.product_ui import build_workspace_menu_text, build_workspace_selector_text
from utils.ui_text import MAIN_MENU_TEXT, build_help_text, build_profile_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("menu"))
async def command_menu(message: Message, db: Database):
    logger.info(f"Команда /menu от {message.from_user.id}")
    user = await db.get_user(message.from_user.id)
    role = user.get("role") if user else None
    account = await db.get_account()
    account_user = await db.get_account_user(message.from_user.id, account["id"]) if account else None
    ui_snapshot = await db.get_resolved_ui_config(db.require_account_id()) if hasattr(db, "get_resolved_ui_config") else {}
    await message.answer(
        build_workspace_menu_text(dict(account or {}), dict(account_user or {}), MAIN_MENU_TEXT),
        reply_markup=get_main_menu_keyboard(
            role,
            is_platform_admin=message.from_user.id == config.ADMIN_ID,
            ui_config=resolve_ui_payload(ui_snapshot),
        ),
    )


@router.message(Command("help"))
async def command_help(message: Message, db: Database):
    logger.info(f"Команда /help от {message.from_user.id}")
    ui_snapshot = await db.get_resolved_ui_config(db.require_account_id()) if hasattr(db, "get_resolved_ui_config") else {}
    ui_payload = resolve_ui_payload(ui_snapshot)
    await message.answer(
        build_help_text(
            tone=ui_tone(ui_payload),
            product_name=ui_display_name(ui_payload),
            intro_text=ui_copy_text(ui_payload, "help_intro"),
        )
    )


@router.message(Command("profile"))
async def command_profile(message: Message, db: Database):
    logger.info(f"Команда /profile от {message.from_user.id}")
    user = await db.get_user(message.from_user.id)

    if not user:
        await message.answer(
            "⚠️ Вы не зарегистрированы. Используйте /start.",
            reply_markup=back_to_menu_keyboard,
        )
        return

    balance = await db.get_student_lesson_balance(message.from_user.id) if user["role"] == "student" else 0
    next_lessons = await db.get_active_lessons(message.from_user.id) if user["role"] == "student" else []
    next_lesson = next_lessons[0]["lesson_date"] if next_lessons and next_lessons[0].get("lesson_date") else None
    children = None
    if user["role"] == "parent":
        children = await db.get_parent_children(message.from_user.id)
    text = build_profile_text(
        user,
        balance,
        next_lesson=next_lesson,
        reminders=user.get("lesson_reminders"),
        children=children,
    )

    if user["role"] == "student":
        kb = profile_keyboard
    elif user["role"] == "parent":
        kb = parent_profile_keyboard
    else:
        kb = back_to_menu_keyboard
    await message.answer(text, reply_markup=kb)


@router.message(Command("workspace"))
async def command_workspace(message: Message, db: Database):
    memberships = await db.get_identity_memberships(telegram_id=message.from_user.id)
    account = await db.get_account()
    identity_snapshot = await db.get_identity_workspace_snapshot(telegram_id=message.from_user.id)
    await message.answer(
        build_workspace_selector_text(
            memberships=[dict(item) for item in memberships],
            current_account_id=account["id"] if account else None,
            identity=identity_snapshot.get("identity"),
        ),
        reply_markup=make_workspace_selector_keyboard([dict(item) for item in memberships], account["id"] if account else None),
    )


@router.callback_query(lambda c: c.data == "workspace:selector")
async def workspace_selector(callback_query, db: Database):
    memberships = await db.get_identity_memberships(telegram_id=callback_query.from_user.id)
    account = await db.get_account()
    identity_snapshot = await db.get_identity_workspace_snapshot(telegram_id=callback_query.from_user.id)
    await callback_query.message.edit_text(
        build_workspace_selector_text(
            memberships=[dict(item) for item in memberships],
            current_account_id=account["id"] if account else None,
            identity=identity_snapshot.get("identity"),
        ),
        reply_markup=make_workspace_selector_keyboard([dict(item) for item in memberships], account["id"] if account else None),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("workspace:switch:"))
async def workspace_switch(callback_query, db: Database):
    target_account_id = int(callback_query.data.split(":")[2])
    memberships = await db.get_identity_memberships(telegram_id=callback_query.from_user.id)
    membership = next((item for item in memberships if item["account_id"] == target_account_id), None)
    if not membership:
        await callback_query.answer("Этот аккаунт вам недоступен.", show_alert=True)
        return

    await db.set_last_active_account(callback_query.from_user.id, target_account_id)
    token = db.push_account_context(target_account_id)
    try:
        user = await db.get_user(callback_query.from_user.id)
        role = user.get("role") if user else membership.get("role")
        account = await db.get_account()
        account_user = await db.get_account_user(callback_query.from_user.id, target_account_id)
        ui_snapshot = await db.get_resolved_ui_config(target_account_id) if hasattr(db, "get_resolved_ui_config") else {}
        await callback_query.message.edit_text(
            build_workspace_menu_text(dict(account or {}), dict(account_user or {}), MAIN_MENU_TEXT),
            reply_markup=get_main_menu_keyboard(
                role,
                is_platform_admin=callback_query.from_user.id == config.ADMIN_ID,
                ui_config=resolve_ui_payload(ui_snapshot),
            ),
        )
    finally:
        db.reset_account_context(token)
    await callback_query.answer("Аккаунт переключён.")
