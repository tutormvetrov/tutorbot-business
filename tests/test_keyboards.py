import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from keyboards.inline import (
    admin_education_keyboard,
    admin_keyboard,
    admin_service_keyboard,
    admin_students_keyboard,
    make_brand_tone_keyboard,
    make_admin_speech_styles_keyboard,
    make_admin_student_card_keyboard,
    make_contacts_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lesson_presence_keyboard,
    make_reschedule_offer_keyboard,
)


class KeyboardHelpersTest(unittest.TestCase):
    def test_lesson_presence_keyboard_contains_expected_buttons(self):
        kb = make_lesson_presence_keyboard(42)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]

        self.assertIn("✅ Буду вовремя", texts)
        self.assertIn("⏱ Немного задержусь", texts)
        self.assertIn("✉️ Написать преподавателю", texts)
        self.assertIn("lesson_presence:on_time:42", callbacks)
        self.assertIn("lesson_presence:late:42", callbacks)
        self.assertIn("reply:lesson:42", callbacks)

    def test_contacts_keyboard_includes_vk_link_when_present(self):
        kb = make_contacts_keyboard(vk_call_url="https://vk.com/call/join/example")
        self.assertEqual(kb.inline_keyboard[0][0].text, "📞 VK Звонок")
        self.assertEqual(
            kb.inline_keyboard[0][0].url,
            "https://vk.com/call/join/example",
        )

    def test_contacts_keyboard_labels_google_meet_as_vpn_option(self):
        kb = make_contacts_keyboard(google_meet_url="https://meet.google.com/example-room")
        self.assertEqual(kb.inline_keyboard[0][0].text, "📹 Google Meet (VPN)")
        self.assertEqual(
            kb.inline_keyboard[0][0].url,
            "https://meet.google.com/example-room",
        )

    def test_admin_student_card_keyboard_exposes_quick_actions(self):
        kb = make_admin_student_card_keyboard(
            telegram_id=555,
            page=2,
            lesson_format="offline",
            speech_style="formal",
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✉️ Написать", texts)
        self.assertIn("💰 Оплаты", texts)
        self.assertIn("➕ Урок", texts)
        self.assertIn("💳 Добавить оплату", texts)
        self.assertIn("📚 Задать ДЗ", texts)
        self.assertTrue(any("Переключить на онлайн" in text for text in texts))
        self.assertTrue(any("Обращение: на Вы" in text for text in texts))
        self.assertIn("admin:quick:add_lesson:555:2", callbacks)
        self.assertIn("admin:quick:add_payment:555:2", callbacks)
        self.assertIn("admin:quick:add_homework:555:2", callbacks)
        self.assertIn("admin:write_to_student:555:2", callbacks)
        self.assertIn("admin:student_speech_style:555:2:informal", callbacks)

    def test_lesson_delete_keyboard_offers_calendar_option_when_linked(self):
        kb = make_lesson_delete_confirm_keyboard(42, can_delete_from_calendar=True)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🗑 Удалить только из бота", texts)
        self.assertIn("🗓 Удалить из бота и Calendar", texts)
        self.assertIn("lesson_delete:42:db", callbacks)
        self.assertIn("lesson_delete:42:calendar", callbacks)

    def test_admin_home_keyboard_contains_only_section_navigation(self):
        texts = [button.text for row in admin_keyboard.inline_keyboard for button in row]

        self.assertEqual(
            texts,
            [
                "👥 Ученики",
                "📚 Учебный процесс",
                "📢 Коммуникации",
                "⚙️ Сервис",
                "◀️ Главное меню",
            ],
        )

    def test_admin_section_keyboards_are_grouped_by_context(self):
        student_texts = [button.text for row in admin_students_keyboard.inline_keyboard for button in row]
        education_texts = [button.text for row in admin_education_keyboard.inline_keyboard for button in row]
        service_texts = [button.text for row in admin_service_keyboard.inline_keyboard for button in row]

        self.assertIn("📋 Список учеников", student_texts)
        self.assertIn("👤 Добавить ученика", student_texts)
        self.assertIn("🗣 Обращение", student_texts)
        self.assertIn("🗑 Деактивировать", student_texts)
        self.assertIn("💀 Полный сброс", student_texts)
        self.assertIn("➕ Добавить занятие", education_texts)
        self.assertIn("🗑 Удалить занятие", education_texts)
        self.assertIn("📚 Задать ДЗ", education_texts)
        self.assertIn("📋 Активные ДЗ", education_texts)
        self.assertIn("🎨 Тональность бренда", service_texts)

    def test_admin_speech_styles_keyboard_shows_toggle_targets(self):
        kb = make_admin_speech_styles_keyboard(
            [
                {"telegram_id": 1, "full_name": "Анна", "speech_style": "formal"},
                {"telegram_id": 2, "full_name": "Илья", "speech_style": "informal"},
            ]
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertTrue(any("переключить на ты" in text for text in texts))
        self.assertTrue(any("переключить на Вы" in text for text in texts))
        self.assertIn("admin:speech_style_toggle:1:informal", callbacks)
        self.assertIn("admin:speech_style_toggle:2:formal", callbacks)

    def test_reschedule_offer_keyboard_contains_slots_and_reply_button(self):
        kb = make_reschedule_offer_keyboard(
            [("202604041400", "04.04 14:00"), ("202604051130", "05.04 11:30")]
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🗓 04.04 14:00", texts)
        self.assertIn("🗓 05.04 11:30", texts)
        self.assertIn("✉️ Написать преподавателю", texts)
        self.assertIn("reschedule_pick:202604041400", callbacks)

    def test_brand_tone_keyboard_marks_current_value(self):
        kb = make_brand_tone_keyboard("warm")
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("• Тёплый", texts)


if __name__ == "__main__":
    unittest.main()
