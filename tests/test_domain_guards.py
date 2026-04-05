import asyncio
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from tests.helpers import DummyBot
from utils.db_api.business import DatabaseBusinessMixin
from utils.db_api.lessons import DatabaseLessonMixin
from utils.db_api.payments import DatabasePaymentMixin
from utils.domain_errors import CapabilityLockedError, PaymentIntegrityError, QuotaExceededError
from utils.scheduler import payment_reminder_job


class _ResolvedSubscription:
    def __init__(self, *, capabilities=None, limits=None):
        self.capabilities = capabilities or {}
        self.limits = limits or {}


class _CapacityBusinessFake(DatabaseBusinessMixin):
    def __init__(self, *, active_students=0, active_groups=0, existing_user=None, team_roles=True, team_members=1, active_team_members=0, active_team_invites=0):
        self._active_students = active_students
        self._active_groups = active_groups
        self._existing_user = existing_user
        self._team_roles = team_roles
        self._team_members = team_members
        self._active_team_members = active_team_members
        self._active_team_invites = active_team_invites
        self.account_id = 1

    def require_account_id(self):
        return self.account_id

    def push_account_context(self, account_id):
        previous = self.account_id
        self.account_id = account_id
        return previous

    def reset_account_context(self, token):
        self.account_id = token

    async def execute(self, *args, **kwargs):
        return None

    async def get_account_billing_snapshot(self):
        return {
            "resolved": _ResolvedSubscription(
                capabilities={"groups": True},
                limits={"active_students": 1, "groups": 2, "team_members": self._team_members},
            )
        }

    async def get_account_analytics_snapshot(self):
        return {
            "active_students": self._active_students,
            "active_groups": self._active_groups,
        }

    async def get_user(self, telegram_id):
        return self._existing_user

    async def _resolve_subscription_for_account(self, account_id: int, connection=None):
        return (
            _ResolvedSubscription(
                capabilities={"team_roles": self._team_roles},
                limits={"team_members": self._team_members},
            ),
            {},
        )

    async def _count_active_team_members(self, account_id: int, connection=None) -> int:
        return self._active_team_members

    async def _count_active_team_invites(self, account_id: int, connection=None) -> int:
        return self._active_team_invites


class _ResolveContextNoFallbackFake(DatabaseBusinessMixin):
    def __init__(self):
        self.fallback_queries = 0

    async def execute(self, query, *args, **kwargs):
        if "FROM users" in query:
            self.fallback_queries += 1
        return None

    async def get_global_identity(self, telegram_id: int):
        return {"id": 10, "telegram_id": telegram_id, "last_active_account_id": None}

    async def get_account_by_id(self, account_id: int):
        if account_id == 1:
            return {"id": 1, "name": "Default", "status": "active"}
        return None

    async def get_account_user_by_identity(self, identity_id: int, account_id: int):
        return None

    async def get_account_user(self, telegram_id: int, account_id: int | None = None):
        return None

    async def get_identity_memberships(self, telegram_id: int | None = None, identity_id: int | None = None):
        return []

    async def get_account_invite_by_token(self, token: str, include_inactive: bool = False):
        return None

    async def get_default_account(self):
        return {"id": 1, "name": "Default", "status": "active"}


class _PaymentDeleteFake(DatabasePaymentMixin):
    def __init__(self, payment):
        self.payment = payment
        self.executed = []

    def require_account_id(self):
        return 1

    async def get_payment_by_id(self, payment_id: int):
        return self.payment

    async def execute(self, query, *args, **kwargs):
        self.executed.append((query, args, kwargs))
        return "DELETE 1"


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _LessonConn:
    def __init__(self, *, payment_exists: bool):
        self.payment_exists = payment_exists
        self.executed = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        if "SELECT id, status, balance_consumed" in query:
            return {"id": 9, "status": "active", "balance_consumed": False}
        if "SELECT id FROM payments" in query:
            return {"id": 44} if self.payment_exists else None
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _LessonPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class _LessonCompletionFake(DatabaseLessonMixin):
    def __init__(self, conn):
        self.pool = _LessonPool(conn)

    def require_account_id(self):
        return 1

    async def get_user_row_id(self, telegram_id: int):
        return 42


class _MultiAccountSchedulerFake:
    def __init__(self):
        self.account_id = None

    async def list_active_accounts(self):
        return [{"id": 1}, {"id": 2}]

    def push_account_context(self, account_id):
        previous = self.account_id
        self.account_id = account_id
        return previous

    def reset_account_context(self, token):
        self.account_id = token

    def require_account_id(self):
        return self.account_id

    async def get_resolved_ui_config(self, account_id):
        return {}

    async def get_students_with_balances(self):
        if self.account_id == 1:
            return [{"telegram_id": 11, "full_name": "Анна", "lesson_balance": 0, "speech_style": "formal"}]
        if self.account_id == 2:
            return [{"telegram_id": 22, "full_name": "Борис", "lesson_balance": 0, "speech_style": "formal"}]
        return []

    async def get_account_operator_chat_ids(self):
        return [100 + int(self.account_id or 0)]


class BusinessGuardTest(unittest.TestCase):
    def test_student_capacity_enforces_plan_limit(self):
        fake = _CapacityBusinessFake(active_students=1)

        with self.assertRaises(QuotaExceededError):
            asyncio.run(fake.ensure_student_capacity(telegram_id=9001))

    def test_team_capacity_requires_team_roles_capability(self):
        fake = _CapacityBusinessFake(team_roles=False, active_team_members=0)

        with self.assertRaises(CapabilityLockedError):
            asyncio.run(fake.ensure_team_member_capacity("manager", telegram_id=5001))

    def test_resolve_account_context_no_longer_uses_legacy_users_fallback(self):
        fake = _ResolveContextNoFallbackFake()

        resolved = asyncio.run(fake.resolve_account_context(telegram_id=555))

        self.assertEqual(resolved["account"]["id"], 1)
        self.assertIsNone(resolved["account_user"])
        self.assertEqual(fake.fallback_queries, 0)


class PaymentGuardTest(unittest.TestCase):
    def test_delete_payment_rejects_consumed_payment(self):
        fake = _PaymentDeleteFake({"id": 7, "lessons_count": 4, "lessons_remaining": 1})

        with self.assertRaises(PaymentIntegrityError):
            asyncio.run(fake.delete_payment(7))

    def test_delete_payment_allows_pristine_payment(self):
        fake = _PaymentDeleteFake({"id": 7, "lessons_count": 4, "lessons_remaining": 4})

        deleted = asyncio.run(fake.delete_payment(7))

        self.assertTrue(deleted)
        self.assertEqual(len(fake.executed), 1)


class LessonCompletionGuardTest(unittest.TestCase):
    def test_complete_lesson_keeps_unconsumed_lesson_when_payment_missing(self):
        conn = _LessonConn(payment_exists=False)
        fake = _LessonCompletionFake(conn)

        result = asyncio.run(fake.complete_lesson(9, 7001))

        self.assertEqual(result["reason"], "awaiting_payment")
        executed_queries = "\n".join(query for query, _args in conn.executed)
        self.assertIn("SET status = 'completed'", executed_queries)
        self.assertNotIn("SET balance_consumed = true", executed_queries)


class SchedulerAccountIterationTest(unittest.IsolatedAsyncioTestCase):
    async def test_payment_reminder_runs_for_each_active_account(self):
        bot = DummyBot()
        db = _MultiAccountSchedulerFake()

        await payment_reminder_job(bot, db, "morning")

        self.assertEqual(
            [item.chat_id for item in bot.sent_messages],
            [11, 101, 22, 102],
        )


if __name__ == "__main__":
    unittest.main()
