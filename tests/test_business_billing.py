import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from keyboards.inline import make_billing_overrides_keyboard, make_recipient_select_keyboard, make_workspace_selector_keyboard
from keyboards.inline import get_main_menu_keyboard
from utils.db_api.business import DatabaseBusinessMixin
from utils.db_api.postgresql import Database
from utils.db_api.users import DatabaseUserMixin
from utils.capabilities import resolve_subscription
from utils.product_ui import (
    build_domain_user_refs_text,
    build_identity_split_text,
    build_invites_text,
    build_subscription_text,
    build_support_text,
    build_team_text,
    build_workspace_selector_text,
)
from utils.workspace import (
    build_invite_start_link,
    extract_invite_token,
    has_workspace_admin_access,
    has_workspace_billing_access,
    push_workspace_context,
    reset_workspace_context,
    workspace_role_label,
)


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

    def test_role_aware_keyboard_for_manager_exposes_workspace_admin_tools(self):
        kb = get_main_menu_keyboard("manager")
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("🛠 Панель", texts)
        self.assertIn("🧭 Workspace", texts)
        self.assertIn("💼 Продукт", texts)
        self.assertNotIn("📅 Расписание", texts)

    def test_workspace_selector_text_mentions_last_active_account(self):
        text = build_workspace_selector_text(
            memberships=[
                {"account_id": 2, "account_name": "Scale Studio", "role": "manager"},
                {"account_id": 7, "account_name": "Exam Club", "role": "assistant"},
            ],
            current_account_id=2,
            identity={"full_name": "Анна Оператор", "last_active_account_id": 2},
        )

        self.assertIn("Workspace Selector", text)
        self.assertIn("Last active account: <b>2</b>", text)
        self.assertIn("Scale Studio", text)
        self.assertIn("Exam Club", text)

    def test_workspace_selector_keyboard_marks_current_workspace(self):
        kb = make_workspace_selector_keyboard(
            [
                {"account_id": 2, "account_name": "Scale Studio", "role": "manager"},
                {"account_id": 7, "account_name": "Exam Club", "role": "assistant"},
            ],
            current_account_id=2,
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("✅ Scale Studio · Менеджер", texts)
        self.assertIn("🏢 Exam Club · Ассистент", texts)

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
            "product_name": "TutorScalebot",
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
                "identity_workspace": {
                    "identity": {
                        "telegram_id": 55,
                        "full_name": "Оператор Demo",
                        "last_active_account_id": 1,
                    },
                    "memberships": [
                        {"account_id": 1, "account_name": "Demo Workspace", "role": "owner"},
                        {"account_id": 2, "account_name": "Second Workspace", "role": "manager"},
                    ],
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
        self.assertIn("Identity across workspaces", text)
        self.assertIn("Second Workspace", text)
        self.assertIn("users: account=5, other=0, null=0", text)

    def test_team_text_mentions_role_layers(self):
        text = build_team_text(
            {"name": "Scale Studio"},
            [
                {"display_name": "Анна", "role": "owner", "username": "anna"},
                {"display_name": "Павел", "role": "manager", "username": "pavel"},
            ],
            current_role="manager",
        )

        self.assertIn("Команда workspace", text)
        self.assertIn("Scale Studio", text)
        self.assertIn("Ваш текущий доступ: <b>Менеджер</b>", text)
        self.assertIn("@anna", text)

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


class _ResolveContextFake(DatabaseBusinessMixin):
    def __init__(self):
        self.accounts = {
            1: {"id": 1, "name": "Alpha", "status": "active"},
            2: {"id": 2, "name": "Beta", "status": "active"},
        }
        self.identity = {"id": 10, "telegram_id": 555, "last_active_account_id": 2}
        self.memberships = [
            {"account_id": 1, "role": "owner", "account_name": "Alpha"},
            {"account_id": 2, "role": "manager", "account_name": "Beta"},
        ]

    async def execute(self, *args, **kwargs):
        return None

    async def get_global_identity(self, telegram_id: int):
        return self.identity if telegram_id == 555 else None

    async def get_global_identity_by_id(self, identity_id: int):
        return self.identity if identity_id == 10 else None

    async def get_account_by_id(self, account_id: int):
        return self.accounts.get(account_id)

    async def get_account_user_by_identity(self, identity_id: int, account_id: int):
        for membership in self.memberships:
            if identity_id == 10 and membership["account_id"] == account_id:
                return membership
        return None

    async def get_account_user(self, telegram_id: int, account_id: int | None = None):
        if telegram_id != 555:
            return None
        if account_id is None:
            return self.memberships[0]
        for membership in self.memberships:
            if membership["account_id"] == account_id:
                return membership
        return None

    async def get_identity_memberships(self, telegram_id: int | None = None, identity_id: int | None = None):
        if telegram_id == 555 or identity_id == 10:
            return self.memberships
        return []

    async def get_account_invite_by_token(self, token: str, include_inactive: bool = False):
        if token == "joinbeta":
            return {"account_id": 2}
        if token == "joinalpha":
            return {"account_id": 1}
        return None

    async def get_default_account(self):
        return self.accounts[1]


class UserRowIdHelperTest(unittest.TestCase):
    def test_get_user_row_id_returns_projection_id(self):
        fake = _UserRowIdFake({"id": 77, "telegram_id": 123})
        value = asyncio.run(fake.get_user_row_id(123))
        self.assertEqual(value, 77)

    def test_get_user_row_id_returns_none_for_missing_user(self):
        fake = _UserRowIdFake(None)
        value = asyncio.run(fake.get_user_row_id(123))
        self.assertIsNone(value)


class WorkspacePermissionTest(unittest.TestCase):
    def test_workspace_context_helpers_track_role_permissions(self):
        tokens = push_workspace_context(
            {"id": 2, "name": "Beta"},
            {"role": "manager"},
            {"id": 10},
        )
        try:
            self.assertTrue(has_workspace_admin_access(999))
            self.assertFalse(has_workspace_billing_access(999))
        finally:
            reset_workspace_context(tokens)


class ResolveAccountContextTest(unittest.TestCase):
    def test_resolve_account_context_prefers_last_active_workspace(self):
        fake = _ResolveContextFake()

        resolved = asyncio.run(fake.resolve_account_context(telegram_id=555))

        self.assertEqual(resolved["account"]["id"], 2)
        self.assertEqual(resolved["account_user"]["role"], "manager")

    def test_resolve_account_context_prefers_invite_target_when_present(self):
        fake = _ResolveContextFake()

        resolved = asyncio.run(fake.resolve_account_context(telegram_id=555, invite_token="joinalpha"))

        self.assertEqual(resolved["account"]["id"], 1)
        self.assertEqual(resolved["invite"]["account_id"], 1)


if __name__ == "__main__":
    unittest.main()
