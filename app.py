import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import CommandObject
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    Message,
    TelegramObject,
)

from data import config
from loader import bot, dp
from utils.db_api.postgresql import Database
from utils.observability import update_ops_status, write_runtime_event
from utils.ui_text import DEACTIVATED_ACCOUNT_TEXT
from utils.workspace import extract_invite_token, extract_start_payload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Инжектирует БД в хендлеры и блокирует деактивированных пользователей."""
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _extract_invite_token(event: TelegramObject, data: dict[str, Any]) -> str | None:
        if isinstance(event, Message):
            payload = ""
            command = data.get("command")
            if isinstance(command, CommandObject):
                payload = command.args or ""
            if not payload:
                payload = extract_start_payload(getattr(event, "text", ""))
            return extract_invite_token(payload)
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db

        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        invite_token = self._extract_invite_token(event, data)
        resolved_context = await self.db.resolve_account_context(user_id, invite_token=invite_token)
        account = resolved_context.get("account")
        account_user = resolved_context.get("account_user")
        context_token = self.db.push_account_context(account["id"] if account else self.db.account_id)

        try:
            data["account"] = account
            data["account_user"] = account_user
            data["account_invite"] = resolved_context.get("invite")

            db_user = await self.db.get_user(user_id) if user_id else None
            data["db_user"] = db_user

            if user_id and user_id != config.ADMIN_ID and db_user and db_user["is_active"] is False:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("Аккаунт деактивирован.", show_alert=True)
                    except Exception as exc:
                        logger.warning("Не удалось показать alert деактивированному пользователю %s: %s", user_id, exc)
                    if event.message:
                        try:
                            await event.message.answer(DEACTIVATED_ACCOUNT_TEXT)
                        except Exception as exc:
                            logger.warning("Не удалось отправить текст деактивированному пользователю %s: %s", user_id, exc)
                elif isinstance(event, Message):
                    await event.answer(DEACTIVATED_ACCOUNT_TEXT)
                return None

            try:
                return await handler(event, data)
            except Exception as exc:
                logger.exception("Unhandled update error for %s: %s", type(event).__name__, exc)
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⚠️ Внутренняя ошибка. Попробуйте ещё раз.", show_alert=True)
                    except Exception as answer_exc:
                        logger.warning("Не удалось закрыть callback после ошибки: %s", answer_exc)
                elif isinstance(event, Message):
                    try:
                        await event.answer("⚠️ Внутренняя ошибка. Попробуйте ещё раз.")
                    except Exception as answer_exc:
                        logger.warning("Не удалось отправить сообщение об ошибке: %s", answer_exc)
                return None
        finally:
            self.db.reset_account_context(context_token)

async def main():
    import handlers  # noqa: F401 — регистрация роутеров

    # Проверяем токен
    me = await bot.get_me()
    logger.info(f"Бот @{me.username} успешно подключён!")
    write_runtime_event("startup", "ok", bot_username=me.username)

    # Инициализируем БД
    db = Database()
    await db.create_pool()
    await db.create_all_tables()
    await db.sync_all_parent_links()
    logger.info("База данных готова.")
    update_ops_status(status="starting", bot_username=me.username, scheduler="starting")

    # Регистрируем middleware — db попадёт в каждый хендлер как параметр
    dp.update.middleware(DatabaseMiddleware(db))

    # Планировщик задач
    from utils.scheduler import setup_scheduler
    scheduler = setup_scheduler(bot, db)
    scheduler.start()
    logger.info("Планировщик запущен.")
    update_ops_status(status="running", bot_username=me.username, scheduler="running")

    # Публичные команды
    public_commands = [
        BotCommand(command="start",   description="Начать работу с ботом"),
        BotCommand(command="menu",    description="Главное меню"),
        BotCommand(command="help",    description="Помощь"),
        BotCommand(command="profile", description="Мой профиль"),
    ]
    await bot.set_my_commands(public_commands)

    # Команды администратора
    if config.ADMIN_ID:
        admin_commands = public_commands + [
            BotCommand(command="admin", description="Панель администратора"),
            BotCommand(command="sync",  description="Синхронизация Google Calendar"),
        ]
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=config.ADMIN_ID),
            )
        except Exception as e:
            logger.warning(f"Не удалось установить команды для ADMIN_ID: {e}")

    logger.info("Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Останавливаем бота...")
        write_runtime_event("shutdown", "ok")
        update_ops_status(status="stopping", bot_username=me.username, scheduler="stopping")
        scheduler.shutdown()
        if db.pool:
            await db.pool.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
