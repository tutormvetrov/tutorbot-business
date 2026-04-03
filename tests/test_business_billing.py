import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from keyboards.inline import make_billing_overrides_keyboard, make_recipient_select_keyboard
from keyboards.inline import get_main_menu_keyboard
from utils.db_api.postgresql import Database
from utils.db_api.users import DatabaseUserMixin
from utils.capabilities import resolve_subscription
from utils.product_ui import (
    build_domain_user_refs_text,
    build_identity_split_text,
    build_invites_text,
    build_subscription_text,
    build_support_text,
)
from utils.workspace import build_invite_start_link, extract_invite_token, workspace_role_label


class BillingResolverTest(unittest.TestCase):
    def test_trial_expiration_falls_back_to_start_plan(self):
        resolved = resolve_subscription(
            {
                "account_id": 1,
                "plan_code": "practice",
                "status": "trial",
                "trial_ends_at": datetime.now() - timedelta(days=1),
                "paid_until": None,
            }
        )

        self.assertEqual(resolved.effective_status, "trial_expired")
        self.assertEqual(resolved.effective_plan_code, "start")
        self.assertFalse(resolved.capabilities["calendar_sync"])

    def test_manual_override_unlocks_capability(self):
        resolved = resolve_subscription(
            {
                "account_id": 1,
                "plan_code": "start",
                "status": "active",
                "trial_ends_at": None,
                "paid_until": datetime.now() + timedelta(days=30),
            },
            overrides={"calendar_sync": True},
        )

        self.assertTrue(resolved.capabilities["calendar_sync"])
        self.assertIn("groups", resolved.locked_capabilities)


class BillingUiTest(unittest.TestCase):
    def test_subscription_text_lists_locked_features(self):
        resolved = resolve_subscription(
            {
                "account_id": 1,
                "plan_code": "start",
                "status": "active",
                "trial_ends_at": None,
                "paid_until": datetime.now() + timedelta(days=30),
            }
        )
        snapshot = {
            "account": {"name": "Demo Account"},
            "product": {"plans": {"start": {"display_name": "Start"}}},
            "resolved": resolved,
            "overrides": {},
        }

        text = build_subscription_text(snapshot, snapshot["product"])

        self.assertIn("Google Calendar sync", text)
        self.assertIn("weekly digest", text)

    def test_segmented_recipient_keyboard_exposes_segment_buttons(self):
        kb = make_recipient_select_keyboard(
            [{"telegram_id": 1, "full_name": "Анна"}],
            {1},
            segments_enabled=True,
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("🎯 Без баланса", texts)
        self.assertIn("🎯 Без уроков", texts)
        self.assertIn("🎯 С родителями", texts)

    def test_billing_overrides_keyboard_marks_enabled_features(self):
        kb = make_billing_overrides_keyboard({"groups"})
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("✅ Группы", texts)
        self.assertIn("➕ Calendar sync", texts)


class WorkspaceStageFourTest(unittest.TestCase):
    def test_extract_invite_token_supports_join_payload(self):
        self.assertEqual(extract_invite_token("join_demo123"), "demo123")
        self.assertEqual(extract_invite_token("invite_demo123"), "demo123")
        self.assertIsNone(extract_invite_token("random"))

    def test_build_invite_start_link_prefers_bot_username(self):
        self.assertEqual(
            build_invite_start_link("TutorbotDemoBot", "abc123"),
            "https://t.me/TutorbotDemoBot?start=join_abc123",
        )
        self.assertEqual(build_invite_start_link("", "abc123"), "/start join_abc123")

    def test_role_aware_keyboard_for_manager_is_limited(self):
        kb = get_main_menu_keyboard("manager")
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("💼 Продукт", texts)
        self.assertIn("👤 Профиль", texts)
        self.assertNotIn("📅 Расписание", texts)

    def test_account_context_uses_contextvar_and_restores_default(self):
        db = Database()
        db.account_id = 11

        token = db.push_account_context(42)
        self.assertEqual(db.require_account_id(), 42)

        db.reset_account_context(token)
        self.assertEqual(db.require_account_id(), 11)

    def test_invites_text_shows_join_link(self):
        text = build_invites_text(
            {"name": "Demo Workspace"},
            [
                {
                    "id": 7,
                    "role": "assistant",
                    "token": "abc123",
                    "status": "active",
                    "expires_at": datetime(2026, 4, 10, 12, 0),
                    "label": "assistant-seat",
                }
            ],
            bot_username="TutorbotDemoBot",
        )

        self.assertIn("Demo Workspace", text)
        self.assertIn(workspace_role_label("assistant"), text)
        self.assertIn("https://t.me/TutorbotDemoBot?start=join_abc123", text)

    def test_support_text_includes_partition_summary(self):
        resolved = resolve_subscription(
            {
                "account_id": 1,
                "plan_code": "practice",
                "status": "active",
                "trial_ends_at": None,
                "paid_until": datetime.now() + timedelta(days=30),
            }
        )
        product = {
            "product_name": "Tutorbot Business",
            "support_contact": "support@example.com",
            "plans": {
                "practice": {"display_name": "Practice"},
            },
        }
        text = build_support_text(
            {
                "account": {"id": 1, "name": "Demo Workspace", "slug": "demo", "status": "active"},
                "billing": {"resolved": resolved, "product": product},
                "analytics": {
                    "active_students": 3,
                    "active_parents": 2,
                    "active_groups": 1,
                    "lessons_next_7_days": 5,
                },
                "partition": {
                    "healthy": True,
                    "null_account_rows": 0,
                    "tables": {
                        "users": {"account_rows": 5, "other_account_rows": 0, "null_account_rows": 0},
                    },
                },
                "identity_split": {
                    "ready": True,
                    "total_global_identities": 6,
                    "linked_users": 5,
                    "total_memberships": 2,
                    "users_missing_identity": 0,
                    "account_users_missing_identity": 0,
                },
                "domain_user_refs": {
                    "ready": True,
                    "total_missing": 0,
                    "missing": {
                        "lessons.student_user_id": 0,
                    },
                },
                "owner_user": {"full_name": "Owner Demo"},
                "active_members": 2,
                "active_invites_count": 1,
            },
            product,
        )

        self.assertIn("Support Tooling", text)
        self.assertIn("Demo Workspace", text)
        self.assertIn("Data Partitioning", text)
        self.assertIn("Identity Split Readiness", text)
        self.assertIn("Surrogate User Refs", text)
        self.assertIn("users: account=5, other=0, null=0", text)

    def test_identity_split_text_reports_missing_links(self):
        text = build_identity_split_text(
            {
                "ready": False,
                "total_global_identities": 7,
                "linked_users": 4,
                "total_memberships": 3,
                "users_missing_identity": 2,
                "account_users_missing_identity": 1,
            }
        )

        self.assertIn("Есть записи без identity link", text)
        self.assertIn("Global identities: <b>7</b>", text)
        self.assertIn("Users без identity: <b>2</b>", text)

    def test_domain_user_refs_text_reports_missing_surrogate_refs(self):
        text = build_domain_user_refs_text(
            {
                "ready": False,
                "total_missing": 3,
                "missing": {
                    "lessons.student_user_id": 2,
                    "payments.student_user_id": 1,
                },
            }
        )

        self.assertIn("legacy-only строки", text)
        self.assertIn("lessons.student_user_id: <b>2</b>", text)
        self.assertIn("payments.student_user_id: <b>1</b>", text)


class _UserRowIdFake(DatabaseUserMixin):
    def __init__(self, row):
        self.row = row

    def require_account_id(self):
        return 1

    async def get_user(self, telegram_id: int):
        if self.row and self.row["telegram_id"] == telegram_id:
            return self.row
        return None


class UserRowIdHelperTest(unittest.TestCase):
    def test_get_user_row_id_returns_projection_id(self):
        fake = _UserRowIdFake({"id": 77, "telegram_id": 123})
        value = asyncio.run(fake.get_user_row_id(123))
        self.assertEqual(value, 77)

    def test_get_user_row_id_returns_none_for_missing_user(self):
        fake = _UserRowIdFake(None)
        value = asyncio.run(fake.get_user_row_id(123))
        self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()
