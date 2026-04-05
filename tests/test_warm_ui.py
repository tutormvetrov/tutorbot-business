import sys
from datetime import datetime
import inspect
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import admin_add_lesson_quick, admin_lesson_date_entered
from handlers.users.admin_sections.common import restore_admin_view
from handlers.users.admin_sections.homework import admin_add_homework_quick, admin_hw_deadline_entered, admin_hw_description_entered
from handlers.users.admin_sections.students import _render_admin_students_page
from handlers.users.admin_sections.payments import admin_add_payment_quick, admin_payment_amount_entered, admin_payment_count_entered
from handlers.users.callbacks import process_homework, process_homework_list, process_notif_action, process_notif_manage, cancel_fsm
from keyboards.inline import make_homework_list_keyboard
from tests.helpers import DummyBot, DummyCallbackQuery, DummyMessage, DummyState
from utils.ui_text import (
    build_admin_dashboard_text,
    build_contacts_text,
    build_homework_text,
    build_notifications_text,
    build_requisites_text,
)


def _call_with_optional_ui_overrides(func, *args, tone=None, copy=None, **kwargs):
    params = inspect.signature(func).parameters
    if tone is not None and "tone" in params:
        kwargs["tone"] = tone
    if copy is not None:
        if "copy" in params:
            kwargs["copy"] = copy
        elif "copy_overrides" in params:
            kwargs["copy_overrides"] = copy
    return func(*args, **kwargs)


def _keyboard_texts(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


class WarmUiTextTest(unittest.TestCase):
    def test_admin_dashboard_text_uses_snapshot_summary(self):
        text = build_admin_dashboard_text(
            {
                "active_students": 7,
                "lessons_today": 3,
                "unpaid_students": 2,
                "pending_freezes": 1,
                "active_homework": 5,
                "students_without_upcoming_lessons": 4,
            },
            {"scheduler": "running"},
            {"synced_at_local": "01.04.2026 12:00"},
        )

        self.assertIn("Активных учеников: <b>7</b>", text)
        self.assertIn("Уроков сегодня: <b>3</b>", text)
        self.assertIn("Scheduler: <b>running</b>", text)
        self.assertIn("01.04.2026 12:00", text)

    def test_contacts_and_requisites_texts_do_not_dump_raw_urls(self):
        contacts_text = _call_with_optional_ui_overrides(
            build_contacts_text,
            {
                "contacts": {
                    "phone": "+1 555 123",
                    "telegram": "@teacher",
                    "vk_call": "https://vk.com/call/join/example",
                    "google_meet": "https://meet.google.com/example-room",
                    "address": "ул. Пример, 1",
                }
            },
            show_address=True,
            tone="warm",
            copy={"contacts_intro": "Контактный блок"},
        )
        requisites_text = build_requisites_text(
            {
                "rates": ["0 рублей / 60 минут", "0 рублей / 90 минут"],
                "card": "4111 1111 1111 1111",
                "sbp": "+7 900 000-00-00",
            }
        )

        self.assertIn("VK Звонок", contacts_text)
        self.assertIn("VPN", contacts_text)
        self.assertIn("0 рублей / 60 минут", requisites_text)
        self.assertNotIn("https://", contacts_text)
        self.assertNotIn("https://", requisites_text)


class StudentListUiTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_list_uses_short_copy_and_card_buttons(self):
        class FakeDB:
            async def get_students_overview(self):
                return [
                    {
                        "telegram_id": 555,
                        "full_name": "Иван Петров",
                        "language": "Английский",
                        "level": "B1",
                        "lesson_balance": 4,
                        "lesson_format": "online",
                        "first_lesson_date": datetime(2026, 4, 1),
                        "next_lesson_date": datetime(2026, 4, 5, 14, 0),
                    },
                    {
                        "telegram_id": 556,
                        "full_name": "Анна Смирнова",
                        "language": "Французский",
                        "level": "A2",
                        "lesson_balance": 2,
                        "lesson_format": "offline",
                        "first_lesson_date": datetime(2026, 3, 28),
                        "next_lesson_date": None,
                    },
                ]

        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin")
        await _render_admin_students_page(message, FakeDB(), page=0)

        self.assertIn("Откройте карточку кнопкой ниже.", message.edits[-1])
        self.assertIn("В списке оставлены только короткие ориентиры.", message.edits[-1])
        self.assertEqual(message.reply_markups[-1].inline_keyboard[0][0].callback_data, "admin:student_card:555:0")


class HomeworkAndNotificationUxTest(unittest.IsolatedAsyncioTestCase):
    async def test_homework_opens_active_and_switches_between_tabs(self):
        class FakeDB:
            async def get_student_homework(self, user_id, status):
                if status == "active":
                    return [
                        {"id": 1, "title": "Грамматика", "deadline": datetime(2026, 4, 1), "description": None},
                        {"id": 2, "title": "Лексика", "deadline": datetime(2026, 4, 7), "description": None},
                    ]
                return [
                    {"id": 3, "title": "Прошлое задание", "deadline": datetime(2026, 3, 28), "description": "Готово"},
                ]

        message = DummyMessage(user_id=101, full_name="Иван Петров")
        callback = DummyCallbackQuery("homework", message=message, user_id=101, full_name="Иван Петров")

        await process_homework(callback, FakeDB())
        self.assertIn("Активные задания", message.edits[-1])
        self.assertIn("Срочно", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1])[0], "• Активные")

        await process_homework_list(DummyCallbackQuery("hw:done", message=message, user_id=101), FakeDB())
        self.assertIn("Выполненные задания", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1])[0], "📋 Активные")

    async def test_notifications_re_render_after_disable_and_pause(self):
        class FakeDB:
            def __init__(self):
                self.reminders = "enabled"
                self.calls = []

            async def get_user(self, user_id):
                return {"lesson_reminders": self.reminders}

            async def set_lesson_reminders(self, user_id, value):
                self.calls.append(value)
                self.reminders = value

        db = FakeDB()
        message = DummyMessage(user_id=101, full_name="Иван Петров")
        callback = DummyCallbackQuery("notif:manage", message=message, user_id=101, full_name="Иван Петров")

        await process_notif_manage(callback, db)
        self.assertIn("Напоминания о занятиях", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1])[0], "🔕 Пауза на неделю")

        await process_notif_action(DummyCallbackQuery("notif:disable", message=message, user_id=101), db)
        self.assertEqual(db.calls[-1], "disabled")
        self.assertIn("отключены", message.edits[-1])
        self.assertEqual(_keyboard_texts(message.reply_markups[-1])[0], "🔔 Включить")

        await process_notif_action(DummyCallbackQuery("notif:pause_week", message=message, user_id=101), db)
        self.assertTrue(db.calls[-1].startswith("paused_until:"))
        self.assertIn("на паузе", message.edits[-1])


class AdminQuickFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_quick_payment_restores_student_card(self):
        class FakeDB:
            def __init__(self):
                self.payments = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "offline",
                    "lesson_reminders": "enabled",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

            async def add_payment(self, student_id, amount, count):
                self.payments.append((student_id, amount, count))

        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=900, message_id=77)
        callback = DummyCallbackQuery(
            "admin:quick:add_payment:555:2",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        state = DummyState()
        db = FakeDB()

        await admin_add_payment_quick(callback, state)
        self.assertEqual(state.data["student_id"], 555)
        self.assertEqual(state.data["admin_return_view"], "admin:student_card:555:2")

        await admin_payment_amount_entered(DummyMessage("3000", user_id=config.ADMIN_ID, bot=bot), state)
        await admin_payment_count_entered(DummyMessage("3", user_id=config.ADMIN_ID, bot=bot), state, db)

        self.assertEqual(db.payments, [(555, 3000.0, 3)])
        self.assertTrue(bot.edited_messages)
        self.assertEqual(bot.edited_messages[-1].message_id, 77)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)
        self.assertIn("очно", bot.edited_messages[-1].text)

    async def test_admin_quick_homework_restores_student_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "lesson_reminders": "enabled",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

            async def add_homework(self, student_id, title, description, deadline):
                self.calls.append((student_id, title, description, deadline))
                return 777

        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=901, message_id=78)
        callback = DummyCallbackQuery(
            "admin:quick:add_homework:555:1",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        state = DummyState()
        db = FakeDB()

        await admin_add_homework_quick(callback, state)
        self.assertEqual(state.data["admin_return_view"], "admin:student_card:555:1")

        hw_message = DummyMessage(
            "Сделайте <a href=\"https://example.com\">упражнение</a> и пришлите результат.",
            user_id=config.ADMIN_ID,
            bot=bot,
        )
        hw_message.entities = [object()]
        hw_message.html_text = hw_message.text
        await admin_hw_description_entered(hw_message, state)
        deadline_message = DummyMessage("05/04/2026", user_id=config.ADMIN_ID, bot=bot)
        await admin_hw_deadline_entered(deadline_message, state, db)

        self.assertEqual(db.calls[0][0], 555)
        self.assertEqual(db.calls[0][3].strftime("%d.%m.%Y"), "05.04.2026")
        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)
        self.assertIn("Домашнее задание отправлено", deadline_message.answers[-1])

    async def test_admin_quick_lesson_restores_student_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "lesson_reminders": "enabled",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

            async def add_lesson(self, student_id, lesson_date):
                self.calls.append((student_id, lesson_date))

        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=902, message_id=79)
        callback = DummyCallbackQuery(
            "admin:quick:add_lesson:555:1",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        state = DummyState()
        db = FakeDB()

        await admin_add_lesson_quick(callback, state)
        await admin_lesson_date_entered(
            DummyMessage("05.04.2026 14:00", user_id=config.ADMIN_ID, bot=bot),
            state,
            db,
        )

        self.assertEqual(db.calls[0][0], 555)
        self.assertEqual(db.calls[0][1].strftime("%d.%m.%Y %H:%M"), "05.04.2026 14:00")
        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)

    async def test_restore_admin_view_can_return_to_category_and_card(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "lesson_reminders": "enabled",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        bot = DummyBot()
        await restore_admin_view(bot, FakeDB(), 100, 200, "admin:student_card:555:2")
        await restore_admin_view(bot, FakeDB(), 100, 201, "admin:cat:education")

        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[0].text)
        self.assertTrue(any("Учебный процесс" in item.text for item in bot.edited_messages[1:]))


if __name__ == "__main__":
    unittest.main()
