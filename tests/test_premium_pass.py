import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.callbacks import process_freeze_confirm, process_freeze_reason, process_profile_delete_me, process_self_delete_confirm
from handlers.users.admin_sections.broadcast import (
    admin_broadcast_back_preview,
    admin_broadcast_confirm_text,
    admin_broadcast_select,
    admin_broadcast_start,
    admin_broadcast_text_entered,
    bc_send,
    bc_toggle_recipient,
)
from states.registration import AdminBroadcast, FreezeConfirm
from tests.helpers import DummyBot, DummyCallbackQuery, DummyMessage, DummyState
from utils.ui_text import build_action_result_text


def _keyboard_texts(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


class FreezePremiumPassTest(unittest.IsolatedAsyncioTestCase):
    async def test_freeze_reason_and_confirm_flow_is_clear_and_warm(self):
        state = DummyState()
        message = DummyMessage(user_id=101, full_name="Иван Петров")
        callback = DummyCallbackQuery("freeze:illness", message=message, user_id=101, full_name="Иван Петров")

        class FreezeDB:
            async def get_active_lessons(self, user_id):
                return [
                    {"id": 1, "lesson_date": datetime(2026, 4, 3, 12, 0)},
                    {"id": 2, "lesson_date": datetime(2026, 4, 5, 12, 0)},
                ]

        await process_freeze_reason(callback, state, FreezeDB())

        self.assertEqual(state.state.state, "FreezeConfirm:waiting_for_confirm")
        self.assertIn("Подтверждение заморозки", message.edits[-1])
        self.assertIn("Болезнь", message.edits[-1])
        self.assertIn("Будет затронуто", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1]), ["✅ Отправить заявку", "◀️ Назад"])

        class FreezeDB2:
            def __init__(self):
                self.pool = self
                self.fetch_calls = []
                self.execute_calls = []

            def acquire(self):
                return self

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def fetch(self, query, *args):
                self.fetch_calls.append((query, args))
                return [{"id": 1}, {"id": 2}]

            async def execute(self, query, *args):
                self.execute_calls.append((query, args))
                return "OK"

        bot = DummyBot()
        success_message = DummyMessage(user_id=101, full_name="Иван Петров", bot=bot)
        success_callback = DummyCallbackQuery(
            "freeze_confirm:illness",
            message=success_message,
            user_id=101,
            full_name="Иван Петров",
            bot=bot,
        )

        await state.set_state(FreezeConfirm.waiting_for_confirm)
        await state.update_data(freeze_active_count=2)
        await process_freeze_confirm(success_callback, state, FreezeDB2())

        self.assertEqual(state.state, None)
        self.assertTrue(bot.sent_messages)
        self.assertIn("Новая заявка на заморозку", bot.sent_messages[0].text)
        self.assertIn("Заявка на заморозку отправлена", success_message.edits[-1])
        self.assertIn("Затронуто занятий: <b>2</b>", success_message.edits[-1])
        self.assertEqual(_keyboard_texts(success_message.reply_markups[-1]), ["◀️ Главное меню"])


class SelfDeletePremiumPassTest(unittest.IsolatedAsyncioTestCase):
    async def test_self_delete_warning_and_success_cover_student_and_parent(self):
        cases = [
            (
                "student",
                "Удалить профиль",
                "После удаления профиль, занятия, оплаты и домашние задания исчезнут из базы.",
                "Профиль удалён",
            ),
            (
                "parent",
                "Удалить родительский профиль",
                "Профили учеников при этом не удаляются.",
                "Родительский профиль удалён",
            ),
        ]

        for role, title_snippet, body_snippet, success_snippet in cases:
            with self.subTest(role=role):
                user_id = 201 if role == "student" else 202
                bot = DummyBot()

                class FakeDB:
                    def __init__(self):
                        self.deleted = []

                    async def get_user(self, telegram_id):
                        return {
                            "telegram_id": telegram_id,
                            "full_name": "Анна Смирнова" if role == "student" else "Игорь Смирнов",
                            "role": role,
                            "is_active": True,
                        }

                    async def get_user_deletion_snapshot(self, telegram_id):
                        return {
                            "lessons": 4,
                            "homework": 3,
                            "payments_as_student": 2,
                            "payments_as_payer": 1,
                            "calendar_links": 2,
                            "parent_links_as_parent": 3,
                        }

                    async def delete_user_fully(self, telegram_id):
                        self.deleted.append(telegram_id)

                message = DummyMessage(user_id=user_id, full_name="Test", bot=bot)
                callback = DummyCallbackQuery(
                    "profile:delete_me",
                    message=message,
                    user_id=user_id,
                    full_name="Test",
                    bot=bot,
                )

                await process_profile_delete_me(callback, FakeDB())

                self.assertIn(title_snippet, message.edits[-1])
                self.assertIn(body_snippet, message.edits[-1])
                self.assertEqual(_keyboard_texts(message.reply_markups[-1]), ["🗑 Да, удалить профиль", "◀️ Назад в профиль"])

                confirm_callback = DummyCallbackQuery(
                    "self_delete:confirm",
                    message=message,
                    user_id=user_id,
                    full_name="Test",
                    bot=bot,
                )
                await process_self_delete_confirm(confirm_callback, FakeDB())

                self.assertIn(success_snippet, message.edits[-1])
                self.assertEqual(_keyboard_texts(message.reply_markups[-1]), ["◀️ Главное меню"])


class BroadcastPremiumPassTest(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_preview_recipient_select_and_send(self):
        state = DummyState()
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.students = [
                    {"telegram_id": 11, "full_name": "Анна"},
                    {"telegram_id": 22, "full_name": "Борис"},
                ]

            async def get_all_students(self):
                return list(self.students)

        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        preview_message = DummyMessage(
            "Проверьте связи и напомните о переносе урока.",
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await state.set_state(AdminBroadcast.waiting_for_text)
        await admin_broadcast_text_entered(preview_message, state)

        self.assertIn("Предпросмотр рассылки", preview_message.answers[-1])
        self.assertIn("Именно так сообщение увидят", preview_message.answers[-1])
        self.assertIn("✅ К выбору получателей", _keyboard_texts(preview_message.reply_markups[-1])[0])

        await state.set_state(AdminBroadcast.waiting_for_text_confirm)
        await state.update_data(broadcast_text="Проверьте связи и напомните о переносе урока.")
        confirm_callback = DummyCallbackQuery("bc_confirm", message=message, user_id=config.ADMIN_ID, bot=bot)
        await admin_broadcast_confirm_text(confirm_callback, state, FakeDB())

        self.assertIn("Выберите получателей рассылки", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1])[0], "☐ Анна")
        self.assertIn("Сейчас никто не выбран", message.edits[-1])

        toggle_callback = DummyCallbackQuery("bc_toggle:11", message=message, user_id=config.ADMIN_ID, bot=bot)
        await bc_toggle_recipient(toggle_callback, state)
        self.assertIn("Выбрано: <b>1</b>", message.edits[-1])

        back_preview = DummyCallbackQuery("bc_back_preview", message=message, user_id=config.ADMIN_ID, bot=bot)
        await admin_broadcast_back_preview(back_preview, state)
        self.assertIn("Предпросмотр рассылки", message.edits[-1])

        await state.set_state(AdminBroadcast.waiting_for_recipients)
        await state.update_data(
            recipient_ids=[22],
            students_cache=[{"telegram_id": 11, "full_name": "Анна"}, {"telegram_id": 22, "full_name": "Борис"}],
            broadcast_text="Проверьте связи и напомните о переносе урока.",
        )
        send_callback = DummyCallbackQuery("bc_send", message=message, user_id=config.ADMIN_ID, bot=bot)
        await bc_send(send_callback, state)

        self.assertEqual(len(bot.sent_messages), 1)
        self.assertEqual(bot.sent_messages[0].chat_id, 22)
        self.assertEqual(
            bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:broadcast",
        )
        self.assertIn("Рассылка завершена", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1]), ["◀️ К коммуникациям"])

    async def test_broadcast_accepts_gif_and_copies_it_with_reply_button(self):
        state = DummyState()
        bot = DummyBot()
        preview_message = DummyMessage(
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
            animation=object(),
            caption="Смотрите, как это работает.",
        )

        await state.set_state(AdminBroadcast.waiting_for_text)
        await admin_broadcast_text_entered(preview_message, state)

        self.assertIn("GIF-анимация", preview_message.answers[-1])
        data = await state.get_data()

        await state.set_state(AdminBroadcast.waiting_for_recipients)
        await state.update_data(
            recipient_ids=[11],
            students_cache=[{"telegram_id": 11, "full_name": "Анна"}],
            broadcast_mode=data["broadcast_mode"],
            broadcast_preview=data["broadcast_preview"],
            broadcast_source_chat_id=data["broadcast_source_chat_id"],
            broadcast_source_message_id=data["broadcast_source_message_id"],
        )
        send_callback = DummyCallbackQuery(
            "bc_send",
            message=DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )
        await bc_send(send_callback, state)

        self.assertEqual(len(bot.copied_messages), 1)
        self.assertEqual(bot.copied_messages[0].chat_id, 11)
        self.assertEqual(
            bot.copied_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:broadcast",
        )

    async def test_broadcast_empty_recipient_list_is_handled_softly(self):
        state = DummyState()
        bot = DummyBot()

        class EmptyDB:
            async def get_all_students(self):
                return []

        callback = DummyCallbackQuery(
            "admin:broadcast",
            message=DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot),
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_broadcast_start(callback)
        self.assertIn("Рассылка", callback.message.edits[-1])

        select_callback = DummyCallbackQuery("broadcast:illness", message=callback.message, user_id=config.ADMIN_ID, bot=bot)
        await admin_broadcast_select(select_callback, state, EmptyDB())
        self.assertIn("Предпросмотр рассылки", callback.message.edits[-1])

        confirm_callback = DummyCallbackQuery("bc_confirm", message=callback.message, user_id=config.ADMIN_ID, bot=bot)
        await admin_broadcast_confirm_text(confirm_callback, state, EmptyDB())

        self.assertIn("Рассылка пока недоступна", callback.message.edits[-1])
        self.assertEqual(state.state, None)

    async def test_level_test_broadcast_uses_account_scoped_ui_link(self):
        state = DummyState()
        bot = DummyBot()

        class UiScopedDB:
            def require_account_id(self):
                return 7

            async def get_resolved_ui_config(self, account_id):
                return {
                    "resolved": {
                        "branding": {"display_name": "Scale English", "tone": "premium"},
                        "contacts": {"level_test_url": "https://scale.example.com/test"},
                        "requisites": {},
                        "copy": {},
                        "menu": {},
                    }
                }

        callback = DummyCallbackQuery(
            "broadcast:level_test",
            message=DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot),
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_broadcast_select(callback, state, UiScopedDB())

        self.assertIn("https://scale.example.com/test", callback.message.edits[-1])
        data = await state.get_data()
        self.assertIn("https://scale.example.com/test", data["broadcast_preview"])


class BroadcastHelperTextTest(unittest.TestCase):
    def test_action_result_text_remains_warm_and_structured(self):
        text = build_action_result_text(
            "Рассылка отправлена",
            "Сообщение ушло выбранным получателям.",
            next_step="Можно вернуться в панель и продолжить работу.",
        )

        self.assertIn("Рассылка отправлена", text)
        self.assertIn("Сообщение ушло", text)
        self.assertIn("Можно вернуться", text)


if __name__ == "__main__":
    unittest.main()
