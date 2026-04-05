import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.start import _register_admin, command_start
from tests.helpers import DummyConn, DummyMessage, DummyPool, DummyState


class OwnerStartSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_owner_start_shows_single_onboarding_menu(self):
        class FakeDB:
            def __init__(self):
                self.conn = DummyConn()
                self.pool = DummyPool(self.conn)

            def require_account_id(self):
                return 1

            async def ensure_global_identity(self, telegram_id, full_name="", username=None):
                return {"id": 77}

            async def ensure_account_user(self, telegram_id, role):
                return {"telegram_id": telegram_id, "role": role}

            async def ensure_default_subscription(self):
                return None

            async def get_resolved_ui_config(self, account_id):
                return {
                    "resolved": {
                        "branding": {"display_name": "TutorScalebot", "tone": "warm"},
                        "contacts": {},
                        "requisites": {},
                        "copy": {},
                        "menu": {},
                    }
                }

            async def get_account_billing_snapshot(self):
                resolved = type(
                    "Snapshot",
                    (),
                    {
                        "effective_status": "trial",
                        "effective_plan_code": "start",
                        "trial_ends_at": None,
                        "paid_until": None,
                        "is_trial_active": True,
                    },
                )()
                return {"resolved": resolved, "product": {"plans": {"start": {"display_name": "Start"}}}}

        message = DummyMessage("/start", user_id=config.ADMIN_ID, full_name="Owner Demo")

        await _register_admin(message, FakeDB())

        self.assertEqual(len(message.answers), 1)
        self.assertIn("Что сделать сейчас", message.answers[0])

    async def test_returning_owner_with_incomplete_setup_gets_quick_start_reminder(self):
        class FakeDB:
            def require_account_id(self):
                return 1

            async def get_resolved_ui_config(self, account_id):
                return {
                    "resolved": {
                        "branding": {"display_name": "TutorScalebot", "tone": "warm"},
                        "contacts": {"telegram": "@tutorscalebot"},
                        "requisites": {"rates": ["0 рублей / 60 минут"]},
                        "copy": {},
                        "menu": {},
                    }
                }

            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Owner Demo", "role": "owner"}

            async def get_account(self):
                return {"id": 1, "name": "Demo Account"}

            async def get_account_user(self, telegram_id, account_id):
                return {"role": "owner"}

            async def get_account_analytics_snapshot(self):
                return {"active_students": 0, "lessons_next_7_days": 0}

        message = DummyMessage("/start", user_id=5001, full_name="Owner Demo")
        state = DummyState()

        await command_start(message, state, FakeDB())

        self.assertIn("С возвращением", message.answers[0])
        self.assertIn("Быстрый запуск ещё не завершён", message.answers[1])
        self.assertIn("реквизиты", message.answers[1])
        self.assertIn("первого ученика", message.answers[1])

    async def test_returning_owner_with_ready_setup_skips_extra_reminder(self):
        class FakeDB:
            def require_account_id(self):
                return 1

            async def get_resolved_ui_config(self, account_id):
                return {
                    "resolved": {
                        "branding": {"display_name": "TutorScalebot", "tone": "warm"},
                        "contacts": {"telegram": "@tutorscalebot"},
                        "requisites": {
                            "rates": ["0 рублей / 60 минут"],
                            "card": "1111 2222 3333 4444",
                        },
                        "copy": {},
                        "menu": {},
                    }
                }

            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Owner Demo", "role": "owner"}

            async def get_account(self):
                return {"id": 1, "name": "Demo Account"}

            async def get_account_user(self, telegram_id, account_id):
                return {"role": "owner"}

            async def get_account_analytics_snapshot(self):
                return {"active_students": 3, "lessons_next_7_days": 2}

        message = DummyMessage("/start", user_id=5002, full_name="Owner Demo")
        state = DummyState()

        await command_start(message, state, FakeDB())

        self.assertEqual(len(message.answers), 1)
        self.assertIn("С возвращением", message.answers[0])


if __name__ == "__main__":
    unittest.main()
