import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import admin_add_lesson_quick, render_admin_home
from handlers.users.admin_sections.health import _format_health_text
from handlers.users.admin_sections.homework import admin_hw_deadline_entered, admin_hw_description_entered
from handlers.users.admin_sections.payments import admin_add_payment_quick, admin_payment_count_entered
from handlers.users.admin_sections.students import (
    admin_student_format_toggle,
    admin_student_speech_style_toggle,
    admin_write_to_student_send,
    admin_write_to_student_start,
)
from handlers.users.callbacks import (
    cancel_fsm,
    process_homework,
    process_homework_list,
    process_lesson_presence,
    process_notif_action,
)
from handlers.users.start import process_age, process_full_name, process_language, process_level, process_role_choice
from tests.helpers import DummyBot, DummyCallbackQuery, DummyConn, DummyMessage, DummyPool, DummyState
from utils.scheduler import homework_gap_check_job, lesson_reminder_job
from utils.ui_text import build_admin_dashboard_text


class RegistrationFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_registration_flow_advances_and_inserts_student(self):
        state = DummyState()
        role_message = DummyMessage(user_id=101, full_name="Иван Петров")
        role_callback = DummyCallbackQuery("role:student", message=role_message, user_id=101, full_name="Иван Петров")

        await process_role_choice(role_callback, state)
        self.assertEqual(state.data["role"], "student")
        self.assertEqual(state.data["reg_total"], 5)

        await process_full_name(DummyMessage("Иван Петров", user_id=101), state)
        self.assertEqual(state.data["full_name"], "Иван Петров")

        await process_age(DummyMessage("16", user_id=101), state)
        self.assertEqual(state.data["age"], 16)

        await process_language(DummyMessage("хочу учить English", user_id=101), state)
        self.assertEqual(state.data["language"], "Английский")

        class FakeDB:
            def __init__(self):
                self.conn = DummyConn()
                self.pool = DummyPool(self.conn)

        db = FakeDB()
        level_callback = DummyCallbackQuery(
            "level:A1",
            message=DummyMessage(user_id=101, full_name="Иван Петров"),
            user_id=101,
            full_name="Иван Петров",
        )
        await process_level(level_callback, state, db)

        self.assertTrue(level_callback.message.edits)
        self.assertEqual(state.state, None)
        self.assertTrue(db.conn.executed)
        self.assertIn("INSERT INTO users", db.conn.executed[0][0])


class HomeworkFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_homework_flow_keeps_html_links_and_accepts_slash_deadline(self):
        state = DummyState()
        await state.update_data(student_id=555)

        text = (
            "Сделайте упражнение и откройте <a href=\"https://example.com\">ссылку</a>. "
            + ("Дополнительная строка. " * 20)
        )
        message = DummyMessage(text, user_id=1)
        message.entities = [object()]
        message.html_text = text

        await admin_hw_description_entered(message, state)
        self.assertIn("description", state.data)
        self.assertIsNotNone(state.data["description"])
        self.assertIn("<a href=\"https://example.com\">", state.data["description"])

        class FakeDB:
            def __init__(self):
                self.calls = []

            async def add_homework(self, student_id, title, description, deadline):
                self.calls.append((student_id, title, description, deadline))
                return 777

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

        db = FakeDB()
        deadline_message = DummyMessage("05/04/2026", user_id=1)
        await admin_hw_deadline_entered(deadline_message, state, db)

        self.assertEqual(db.calls[0][0], 555)
        self.assertEqual(db.calls[0][3].strftime("%d.%m.%Y"), "05.04.2026")
        self.assertTrue(deadline_message.bot.sent_messages)
        self.assertIn("<a href=\"https://example.com\">", deadline_message.bot.sent_messages[0].text)

    async def test_student_homework_opens_active_and_allows_switch_to_done(self):
        class FakeDB:
            async def get_student_homework(self, user_id, status):
                if status == "active":
                    return [{"id": 1, "title": "Активное ДЗ", "deadline": datetime(2026, 4, 5), "description": None}]
                return [{"id": 2, "title": "Сделано", "deadline": datetime(2026, 4, 1), "description": None}]

        message = DummyMessage(user_id=777)
        callback = DummyCallbackQuery("homework", message=message, user_id=777)
        await process_homework(callback, FakeDB())

        self.assertTrue(message.edits)
        self.assertIn("Активные задания", message.edits[-1])
        self.assertIn("Активное ДЗ", message.edits[-1])

        done_callback = DummyCallbackQuery("hw:done", message=message, user_id=777)
        await process_homework_list(done_callback, FakeDB())
        self.assertIn("Выполненные задания", message.edits[-1])
        self.assertIn("Сделано", message.edits[-1])


class LessonPresenceFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_presence_callback_reports_to_admin(self):
        lesson = {"id": 9, "student_id": 1001, "lesson_date": None}
        conn = DummyConn(fetchrow_result=lesson)

        class FakeDB:
            def __init__(self):
                self.pool = DummyPool(conn)

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров", "role": "student"}

        bot = DummyBot()
        message = DummyMessage(user_id=1001, full_name="Иван Петров", bot=bot)
        callback = DummyCallbackQuery(
            "lesson_presence:on_time:9",
            message=message,
            user_id=1001,
            full_name="Иван Петров",
            bot=bot,
        )

        await process_lesson_presence(callback, FakeDB())

        self.assertTrue(message.reply_markups)
        self.assertTrue(bot.sent_messages)
        self.assertIn("Буду вовремя", bot.sent_messages[0].text)


class StudentAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_format_toggle_updates_db_and_rerenders_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def set_lesson_format(self, student_id, lesson_format):
                self.calls.append((student_id, lesson_format))

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "offline",
                    "speech_style": "formal",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        bot = DummyBot()
        message = DummyMessage(user_id=1, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "admin:student_format:555:0:offline",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_student_format_toggle(callback, FakeDB())

        self.assertEqual(callback.answers[0].text, "Формат переключён: очно")
        self.assertTrue(message.edits)

    async def test_student_speech_style_toggle_updates_db_and_rerenders_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def set_speech_style(self, student_id, speech_style):
                self.calls.append((student_id, speech_style))

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "speech_style": "informal",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        bot = DummyBot()
        message = DummyMessage(user_id=1, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "admin:student_speech_style:555:0:informal",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_student_speech_style_toggle(callback, FakeDB())

        self.assertEqual(callback.answers[0].text, "Обращение переключено: на ты")
        self.assertTrue(message.edits)

    async def test_admin_quick_payment_flow_restores_student_card(self):
        state = DummyState()
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=999, message_id=321)
        callback = DummyCallbackQuery(
            "admin:quick:add_payment:555:2",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_add_payment_quick(callback, state)
        self.assertEqual(state.data["student_id"], 555)
        self.assertEqual(state.data["admin_return_view"], "admin:student_card:555:2")
        self.assertEqual(state.state.state, "AdminAddPayment:waiting_for_payment_amount")

        await state.update_data(amount=3000.0)

        class FakeDB:
            def __init__(self):
                self.calls = []

            async def add_payment(self, student_id, amount, count):
                self.calls.append((student_id, amount, count))

            async def get_user(self, telegram_id):
                return {
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "lesson_reminders": "enabled",
                    "telegram_id": telegram_id,
                }

            async def get_student_lesson_balance(self, student_id):
                return 6

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 8, 15, 30)}]

        await admin_payment_count_entered(DummyMessage("4", user_id=config.ADMIN_ID, bot=bot), state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)
        self.assertIn("Баланс", bot.edited_messages[-1].text)

    async def test_admin_cancel_restores_previous_view(self):
        state = DummyState()
        bot = DummyBot()
        await state.update_data(
            admin_return_view="admin:student_card:555:1",
            admin_origin_chat_id=888,
            admin_origin_message_id=55,
        )

        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "full_name": "Анна Смирнова",
                    "role": "student",
                    "is_active": True,
                    "language": "Французский",
                    "level": "A2",
                    "lesson_format": "offline",
                    "lesson_reminders": "enabled",
                    "telegram_id": telegram_id,
                }

            async def get_student_lesson_balance(self, student_id):
                return 2

            async def get_active_lessons(self, student_id):
                return []

        callback = DummyCallbackQuery("cancel_fsm", user_id=config.ADMIN_ID, bot=bot)
        await cancel_fsm(callback, state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertTrue(bot.edited_messages)
        self.assertIn("Анна Смирнова", bot.edited_messages[-1].text)

    async def test_admin_can_send_sticker_to_student_inside_bot(self):
        state = DummyState()
        bot = DummyBot()

        class FakeDB:
            async def get_user(self, telegram_id):
                if telegram_id == 555:
                    return {"telegram_id": 555, "full_name": "Анна Смирнова", "role": "student"}
                return None

        start_message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        start_callback = DummyCallbackQuery(
            "admin:write_to_student:555",
            message=start_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_write_to_student_start(start_callback, state, FakeDB())
        self.assertEqual(state.state.state, "AdminWriteToStudent:waiting_for_message")
        self.assertIn("Отправьте сообщение для ученика", start_message.answers[-1])

        sticker_message = DummyMessage(
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
            sticker=object(),
        )
        await admin_write_to_student_send(sticker_message, state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertEqual(len(bot.copied_messages), 1)
        self.assertEqual(bot.copied_messages[0].chat_id, 555)
        self.assertEqual(
            bot.copied_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:teacher_message",
        )


class ReminderLogicTest(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_reminder_job_formats_online_and_offline_messages(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.sent = []

            async def get_lessons_for_reminder(self):
                now = datetime.now()
                return [
                    {
                        "id": 1,
                        "telegram_id": 11,
                        "full_name": "Online Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "online",
                        "speech_style": "informal",
                    },
                    {
                        "id": 2,
                        "telegram_id": 22,
                        "full_name": "Offline Formal Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "offline",
                        "speech_style": "formal",
                    },
                    {
                        "id": 3,
                        "telegram_id": 33,
                        "full_name": "Offline Informal Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "offline",
                        "speech_style": "informal",
                    },
                ]

            async def mark_lesson_reminder_sent(self, lesson_id):
                self.sent.append(lesson_id)

        db = FakeDB()
        await lesson_reminder_job(bot, db)

        self.assertEqual(db.sent, [1, 2, 3])
        self.assertEqual(len(bot.sent_messages), 3)
        online_text = bot.sent_messages[0].text
        offline_formal_text = bot.sent_messages[1].text
        offline_informal_text = bot.sent_messages[2].text
        self.assertIn("VK-Звонок", online_text)
        self.assertIn("Google Meet", online_text)
        self.assertIn("VPN", online_text)
        self.assertIn("очный урок", offline_formal_text)
        self.assertIn("через час", offline_formal_text)
        self.assertIn("подтвердите", offline_formal_text.lower())
        self.assertIn("Подтверди", offline_informal_text)

    async def test_homework_gap_check_job_notifies_admin_once_per_lesson(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.marked = []

            async def get_lessons_missing_homework(self):
                return [{
                    "id": 77,
                    "student_id": 555,
                    "full_name": "Анна Смирнова",
                    "lesson_date": datetime(2026, 4, 4, 14, 0),
                    "previous_lesson_date": datetime(2026, 3, 28, 14, 0),
                }]

            async def mark_homework_check_reminder_sent(self, lesson_id):
                self.marked.append(lesson_id)

        db = FakeDB()
        await homework_gap_check_job(bot, db)

        self.assertEqual(db.marked, [77])
        self.assertEqual(len(bot.sent_messages), 1)
        self.assertIn("Проверьте домашнее задание", bot.sent_messages[0].text)
        self.assertIn("Анна Смирнова", bot.sent_messages[0].text)


class NotificationsFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_notification_action_rerenders_same_screen(self):
        class FakeDB:
            def __init__(self):
                self.reminders = "enabled"

            async def set_lesson_reminders(self, user_id, value):
                self.reminders = value

            async def get_user(self, user_id):
                return {"lesson_reminders": self.reminders}

        db = FakeDB()
        message = DummyMessage(user_id=501)
        callback = DummyCallbackQuery("notif:disable", message=message, user_id=501)
        await process_notif_action(callback, db)

        self.assertTrue(message.edits)
        self.assertIn("Текущий статус", message.edits[-1])
        self.assertIn("отключены", message.edits[-1])


class AdminDashboardTest(unittest.IsolatedAsyncioTestCase):
    async def test_render_admin_home_uses_dashboard_snapshot(self):
        class FakeDB:
            async def get_admin_dashboard_snapshot(self):
                return {
                    "active_students": 12,
                    "lessons_today": 4,
                    "unpaid_students": 3,
                    "pending_freezes": 1,
                    "active_homework": 7,
                    "students_without_upcoming_lessons": 2,
                }

        message = DummyMessage(user_id=config.ADMIN_ID)
        await render_admin_home(message, FakeDB())

        self.assertTrue(message.edits)
        self.assertIn("Активных учеников: <b>12</b>", message.edits[-1])
        self.assertIn("Активных ДЗ: <b>7</b>", message.edits[-1])


class HealthFormattingTest(unittest.TestCase):
    def test_health_text_includes_runtime_and_sync_snapshot(self):
        text = _format_health_text(
            7,
            {"synced_at_local": "01.04.2026 12:00", "imported": 3, "updated": 1, "deleted": 0, "skipped": 2},
            {
                "status": "running",
                "scheduler": "running",
                "jobs": {
                    "lesson_reminder": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:05:00+00:00",
                        "sent": 2,
                        "checked": 4,
                    },
                    "homework_reminder": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:00:00+00:00",
                        "sent": 1,
                    },
                },
            },
            [{"event_type": "lesson_reminder", "status": "error"}],
        )

        self.assertIn("Здоровье бота", text)
        self.assertIn("Активных учеников: <b>7</b>", text)
        self.assertIn("01.04.2026 12:00", text)
        self.assertIn("Планировщик напоминаний", text)
        self.assertIn("отправлено=2", text)
        self.assertIn("lesson_reminder", text)
        self.assertIn("error", text)


if __name__ == "__main__":
    unittest.main()
