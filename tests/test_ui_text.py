import sys
from datetime import date, datetime
import inspect
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.ui_text import (
    build_action_result_text,
    build_admin_dashboard_text,
    build_contacts_text,
    build_requisites_text,
    student_freshness_label,
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


class UITextTest(unittest.TestCase):
    def test_contacts_text_hides_raw_urls(self):
        info = {
            "contacts": {
                "phone": "+7 900 000-00-00",
                "telegram": "@teacher",
                "vk_call": "https://vk.com/call/join/example",
                "google_meet": "https://meet.google.com/example",
                "address": "ул. Пушкина, дом Колотушкина",
            }
        }

        text = _call_with_optional_ui_overrides(
            build_contacts_text,
            info,
            show_address=True,
            tone="warm",
            copy={"contacts_intro": "Нужны быстрые способы связи."},
        )

        self.assertIn("Контакты преподавателя", text)
        self.assertIn("Google Meet", text)
        self.assertIn("Очные занятия", text)
        self.assertNotIn("https://", text)

    def test_requisites_text_hides_raw_booking_links(self):
        text = build_requisites_text(
            {
                "rates": ["0 рублей / 60 минут", "0 рублей / 90 минут"],
                "card": "1234 5678 9000 1111",
                "sbp": "+7 900 000-00-00",
            }
        )

        self.assertIn("Реквизиты и стоимость", text)
        self.assertIn("0 рублей / 60 минут", text)
        self.assertIn("Сообщить об оплате", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

    def test_contacts_text_is_ready_for_future_override_signature(self):
        info = {"contacts": {"telegram": "@teacher"}}
        text = _call_with_optional_ui_overrides(
            build_contacts_text,
            info,
            tone="calm",
            copy={"contacts_intro": "Связь через бот"},
        )

        self.assertIn("Контакты преподавателя", text)
        self.assertIn("Telegram", text)

    def test_action_result_text_keeps_warm_service_structure(self):
        text = build_action_result_text(
            "Сообщение отправлено",
            "Преподаватель увидит его в ближайшее время.",
            next_step="Можно вернуться в меню или продолжить с текущего экрана.",
        )

        self.assertIn("Сообщение отправлено", text)
        self.assertIn("Преподаватель увидит его", text)
        self.assertIn("Можно вернуться", text)

    def test_admin_dashboard_text_accepts_sync_report_dict(self):
        text = build_admin_dashboard_text(
            {
                "active_students": 8,
                "lessons_today": 3,
                "unpaid_students": 2,
                "pending_freezes": 1,
                "active_homework": 5,
                "students_without_upcoming_lessons": 4,
            },
            {"scheduler": "running"},
            {"synced_at_local": "01.04.2026 14:30"},
        )

        self.assertIn("Активных учеников: <b>8</b>", text)
        self.assertIn("Уроков сегодня: <b>3</b>", text)
        self.assertIn("Последний sync: <b>01.04.2026 14:30</b>", text)

    def test_student_freshness_switches_after_calendar_month(self):
        first_lesson = datetime(2026, 3, 31, 15, 0)

        self.assertEqual(
            student_freshness_label(first_lesson, today=date(2026, 4, 29)),
            "новый",
        )
        self.assertEqual(
            student_freshness_label(first_lesson, today=date(2026, 4, 30)),
            "старый",
        )


if __name__ == "__main__":
    unittest.main()
