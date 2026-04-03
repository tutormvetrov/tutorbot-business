import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from data import config
from keyboards.inline import (
    back_to_menu_keyboard,
    get_main_menu_keyboard,
    profile_keyboard,
    parent_profile_keyboard,
)
from utils.db_api.postgresql import Database
from utils.ui_text import MAIN_MENU_TEXT, build_help_text, build_profile_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("menu"))
async def command_menu(message: Message, db: Database):
    logger.info(f"Команда /menu от {message.from_user.id}")
    user = await db.get_user(message.from_user.id)
    role = user.get("role") if user else None
    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=get_main_menu_keyboard(role, is_platform_admin=message.from_user.id == config.ADMIN_ID),
    )


@router.message(Command("help"))
async def command_help(message: Message):
    logger.info(f"Команда /help от {message.from_user.id}")
    await message.answer(build_help_text())


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

    balance = await db.get_student_lesson_balance(message.from_user.id)
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
