from __future__ import annotations

import json
from datetime import datetime, timedelta
from copy import deepcopy
from secrets import token_urlsafe

from data.config import get_product_name, load_product_config, load_ui_seed_defaults
from utils.capabilities import build_default_trial_window, normalize_plan_code, resolve_subscription
from utils.domain_errors import CapabilityLockedError, QuotaExceededError, ValidationError
from utils.timezone import account_now_naive, account_today
from utils.workspace import workspace_role_label


_ALLOWED_MENU_CALLBACKS = {
    "back_to_menu",
    "contacts",
    "freeze",
    "homework",
    "parent:children",
    "payment",
    "profile",
    "requisites",
    "schedule",
    "product:hub",
    "product:plans",
    "product:included",
    "product:subscription",
    "product:trial",
    "product:team",
    "admin:setup",
    "workspace:selector",
    "admin:home",
    "admin:team",
    "admin:billing",
    "admin:invites",
    "admin:support",
    "admin:analytics",
    "admin:cat:account",
    "admin:cat:service",
    "admin:cat:system",
    "admin:cat:students",
    "admin:cat:education",
    "admin:cat:communication",
    "admin:sync:system",
    "admin:sync:service",
    "admin:calendar_aliases",
    "admin:calendar_report",
    "admin:health",
    "admin:ui",
    "admin:brand_tone",
    "admin:notes",
}

ACCOUNT_USER_ROLES = {"owner", "manager", "assistant", "student", "parent"}
INVITEABLE_ACCOUNT_ROLES = {"owner", "manager", "assistant"}
TEAM_MEMBER_ROLES = {"owner", "manager", "assistant"}
MANAGED_TEAM_ROLES = {"manager", "assistant"}
OPERATOR_NOTIFICATION_ROLES = ("owner", "manager", "assistant")


def _json_payload(value):
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return deepcopy(value)


def _deep_merge(base, overlay):
    if not isinstance(base, dict):
        base = {}
    result = deepcopy(base)
    if not isinstance(overlay, dict):
        return result
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _normalize_menu_item(item: dict, section: str, index: int) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"Menu item in '{section}' must be an object.")
    item_id = str(item.get("id") or f"{section}_{index}").strip()
    label = str(item.get("label") or "").strip()
    value = str(item.get("value") or "").strip()
    kind = str(item.get("kind") or "callback").strip().lower()
    enabled = bool(item.get("enabled", True))
    order = int(item.get("order", index))
    if not item_id:
        raise ValueError(f"Menu item in '{section}' is missing id.")
    if not label:
        raise ValueError(f"Menu item '{item_id}' in '{section}' is missing label.")
    if kind not in {"callback", "url", "telegram_url"}:
        raise ValueError(f"Menu item '{item_id}' in '{section}' has unsupported kind '{kind}'.")
    if not value:
        raise ValueError(f"Menu item '{item_id}' in '{section}' is missing value.")
    if kind == "callback" and value not in _ALLOWED_MENU_CALLBACKS:
        raise ValueError(f"Menu item '{item_id}' in '{section}' uses unsupported callback '{value}'.")
    return {
        "id": item_id,
        "label": label,
        "value": value,
        "kind": kind,
        "enabled": enabled,
        "order": order,
    }


def _normalize_ui_payload(payload: dict, defaults: dict | None = None) -> dict:
    merged = _deep_merge(defaults or {}, _json_payload(payload))
    menu = merged.get("menu")
    if isinstance(menu, dict):
        normalized_menu = {}
        for section, items in menu.items():
            if not isinstance(items, list):
                raise ValueError(f"Menu section '{section}' must be a list.")
            normalized_menu[section] = [
                _normalize_menu_item(item, section, index)
                for index, item in enumerate(items, start=1)
            ]
        merged["menu"] = normalized_menu
    return merged


class DatabaseBusinessMixin:
    def require_account_id(self) -> int:
        if getattr(self, "account_id", None) is None:
            raise RuntimeError("Database account context is not initialized.")
        return int(self.account_id)

    async def get_global_identity(self, telegram_id: int):
        return await self.execute(
            """
            SELECT *
            FROM global_identities
            WHERE telegram_id = $1
            LIMIT 1
            """,
            telegram_id,
            fetchrow=True,
        )

    async def get_global_identity_by_id(self, identity_id: int):
        return await self.execute(
            """
            SELECT *
            FROM global_identities
            WHERE id = $1
            LIMIT 1
            """,
            identity_id,
            fetchrow=True,
        )

    async def set_last_active_account(
        self,
        telegram_id: int,
        account_id: int | None,
        identity_id: int | None = None,
    ) -> bool:
        identity = (
            await self.get_global_identity_by_id(identity_id)
            if identity_id is not None
            else await self.get_global_identity(telegram_id)
        )
        if not identity:
            return False

        if account_id is not None:
            membership = await self.get_account_user_by_identity(identity["id"], account_id)
            if not membership and telegram_id is not None:
                membership = await self.get_account_user(telegram_id, account_id)
            if not membership:
                return False

        await self.execute(
            """
            UPDATE global_identities
            SET last_active_account_id = $2,
                updated_at = CURRENT_TIMESTAMP,
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            identity["id"],
            account_id,
            execute=True,
        )
        return True

    async def ensure_global_identity(
        self,
        telegram_id: int,
        full_name: str = "",
        username: str | None = None,
    ):
        await self.execute(
            """
            INSERT INTO global_identities (
                telegram_id,
                full_name,
                username,
                status,
                updated_at,
                last_seen_at
            )
            VALUES ($1, $2, $3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), global_identities.full_name),
                username = COALESCE(NULLIF(EXCLUDED.username, ''), global_identities.username),
                status = 'active',
                updated_at = CURRENT_TIMESTAMP,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            telegram_id,
            full_name or "",
            username or "",
            execute=True,
        )
        identity = await self.get_global_identity(telegram_id)
        return dict(identity) if identity else None

    async def get_default_account(self):
        return await self.execute(
            """
            SELECT *
            FROM accounts
            WHERE is_default = true
            ORDER BY id
            LIMIT 1
            """,
            fetchrow=True,
        )

    def _normalize_account_role(self, role: str | None, *, invite_only: bool = False) -> str:
        normalized = (role or "").strip().lower()
        allowed_roles = INVITEABLE_ACCOUNT_ROLES if invite_only else ACCOUNT_USER_ROLES
        if normalized not in allowed_roles:
            raise ValidationError("Недопустимая роль аккаунта.")
        return normalized

    async def list_active_accounts(self) -> list:
        return await self.execute(
            """
            SELECT *
            FROM accounts
            WHERE status = 'active'
            ORDER BY
                CASE WHEN is_default THEN 0 ELSE 1 END,
                id
            """,
            fetch=True,
        )

    async def get_account_timezone(self, account_id: int | None = None) -> str:
        target_account_id = int(account_id or self.require_account_id())
        row = await self.execute(
            """
            SELECT timezone
            FROM accounts
            WHERE id = $1
            """,
            target_account_id,
            fetchrow=True,
        )
        return str(row["timezone"] if row and row["timezone"] else "Europe/Moscow")

    async def get_account_now(self, account_id: int | None = None) -> datetime:
        timezone_name = await self.get_account_timezone(account_id=account_id)
        return account_now_naive(timezone_name)

    async def get_account_today(self, account_id: int | None = None):
        timezone_name = await self.get_account_timezone(account_id=account_id)
        return account_today(timezone_name)

    async def _get_subscription_record_for_account(self, account_id: int, connection=None):
        query = """
            SELECT s.*, p.display_name AS plan_display_name, p.description AS plan_description
            FROM subscriptions s
            JOIN plans p ON p.code = s.plan_code
            WHERE s.account_id = $1
        """
        row = await (
            connection.fetchrow(query, account_id)
            if connection is not None
            else self.execute(query, account_id, fetchrow=True)
        )
        return dict(row) if row else None

    async def _get_feature_overrides_for_account(self, account_id: int, connection=None) -> dict[str, bool]:
        query = """
            SELECT capability, is_enabled
            FROM account_feature_overrides
            WHERE account_id = $1
            ORDER BY capability
        """
        rows = await (
            connection.fetch(query, account_id)
            if connection is not None
            else self.execute(query, account_id, fetch=True)
        )
        return {row["capability"]: bool(row["is_enabled"]) for row in rows}

    async def _resolve_subscription_for_account(self, account_id: int, connection=None):
        subscription = await self._get_subscription_record_for_account(account_id, connection=connection)
        overrides = await self._get_feature_overrides_for_account(account_id, connection=connection)
        return resolve_subscription(subscription, overrides=overrides), overrides

    async def _count_active_team_members(self, account_id: int, connection=None) -> int:
        query = """
            SELECT COUNT(*)::int
            FROM account_users au
            JOIN accounts a
              ON a.id = au.account_id
            WHERE au.account_id = $1
              AND au.status = 'active'
              AND a.status = 'active'
              AND au.role = ANY($2::text[])
        """
        params = (account_id, list(TEAM_MEMBER_ROLES))
        value = await (
            connection.fetchval(query, *params)
            if connection is not None
            else self.execute(query, *params, fetchval=True)
        )
        return int(value or 0)

    async def _count_active_team_invites(self, account_id: int, connection=None) -> int:
        query = """
            SELECT COUNT(*)::int
            FROM account_invites
            WHERE account_id = $1
              AND role = ANY($2::text[])
              AND status = 'active'
              AND redeemed_at IS NULL
              AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
        """
        params = (account_id, list(MANAGED_TEAM_ROLES))
        value = await (
            connection.fetchval(query, *params)
            if connection is not None
            else self.execute(query, *params, fetchval=True)
        )
        return int(value or 0)

    async def get_account_operator_chat_ids(
        self,
        roles: tuple[str, ...] = OPERATOR_NOTIFICATION_ROLES,
        account_id: int | None = None,
    ) -> list[int]:
        target_account_id = int(account_id or self.require_account_id())
        rows = await self.execute(
            """
            SELECT DISTINCT au.telegram_id, au.role
            FROM account_users au
            JOIN accounts a
              ON a.id = au.account_id
            WHERE au.account_id = $1
              AND au.status = 'active'
              AND a.status = 'active'
              AND au.telegram_id IS NOT NULL
              AND au.role = ANY($2::text[])
            ORDER BY
                CASE au.role
                    WHEN 'owner' THEN 1
                    WHEN 'manager' THEN 2
                    WHEN 'assistant' THEN 3
                    ELSE 9
                END,
                au.telegram_id
            """,
            target_account_id,
            list(roles),
            fetch=True,
        )
        recipients = [int(row["telegram_id"]) for row in rows if row["telegram_id"]]
        if recipients:
            return recipients
        account = await self.get_account_by_id(target_account_id)
        owner_user_id = (account or {}).get("owner_user_id") if account else None
        return [int(owner_user_id)] if owner_user_id else []

    async def ensure_student_capacity(
        self,
        telegram_id: int | None = None,
        *,
        is_internal: bool = False,
        account_id: int | None = None,
    ):
        if is_internal:
            return
        target_account_id = int(account_id or self.require_account_id())
        token = None
        if account_id is not None:
            token = self.push_account_context(target_account_id)
        try:
            snapshot = await self.get_account_billing_snapshot()
            limit = snapshot["resolved"].limits.get("active_students")
            if limit is None:
                return
            existing = await self.get_user(telegram_id) if telegram_id is not None else None
            if existing:
                existing = dict(existing)
            if (
                existing
                and existing["role"] == "student"
                and existing["is_active"]
                and not bool(existing.get("is_internal_account"))
            ):
                return
            analytics = await self.get_account_analytics_snapshot()
            if int(analytics.get("active_students") or 0) >= int(limit):
                raise QuotaExceededError(
                    f"Лимит активных учеников для текущего тарифа достигнут: {limit}."
                )
        finally:
            if token is not None:
                self.reset_account_context(token)

    async def ensure_team_member_capacity(
        self,
        role: str,
        *,
        telegram_id: int | None = None,
        account_id: int | None = None,
        include_pending_invites: bool = False,
        connection=None,
    ):
        normalized_role = self._normalize_account_role(role)
        if normalized_role not in MANAGED_TEAM_ROLES:
            return
        target_account_id = int(account_id or self.require_account_id())
        resolved, _ = await self._resolve_subscription_for_account(target_account_id, connection=connection)
        if not resolved.capabilities.get("team_roles", False):
            raise CapabilityLockedError("Командные роли недоступны на текущем тарифе.")
        limit = resolved.limits.get("team_members")
        if limit is None:
            return
        existing = None
        if telegram_id is not None:
            existing_query = """
                SELECT role, status
                FROM account_users
                WHERE account_id = $1
                  AND telegram_id = $2
                ORDER BY id
                LIMIT 1
            """
            existing = await (
                connection.fetchrow(existing_query, target_account_id, telegram_id)
                if connection is not None
                else self.execute(existing_query, target_account_id, telegram_id, fetchrow=True)
            )
        if existing:
            existing = dict(existing)
        if existing and existing["status"] == "active" and existing["role"] in TEAM_MEMBER_ROLES:
            return
        current_members = await self._count_active_team_members(target_account_id, connection=connection)
        if include_pending_invites:
            current_members += await self._count_active_team_invites(target_account_id, connection=connection)
        if int(current_members) >= int(limit):
            raise QuotaExceededError(
                f"Лимит командных слотов для текущего тарифа достигнут: {limit}."
            )

    async def ensure_group_capacity(self, *, account_id: int | None = None):
        target_account_id = int(account_id or self.require_account_id())
        token = None
        if account_id is not None:
            token = self.push_account_context(target_account_id)
        try:
            snapshot = await self.get_account_billing_snapshot()
            if not snapshot["resolved"].capabilities.get("groups", False):
                raise CapabilityLockedError("Группы недоступны на текущем тарифе.")
            limit = snapshot["resolved"].limits.get("groups")
            if limit is None:
                return
            analytics = await self.get_account_analytics_snapshot()
            if int(analytics.get("active_groups") or 0) >= int(limit):
                raise QuotaExceededError(f"Лимит групп для текущего тарифа достигнут: {limit}.")
        finally:
            if token is not None:
                self.reset_account_context(token)

    async def get_account_by_id(self, account_id: int):
        return await self.execute(
            """
            SELECT *
            FROM accounts
            WHERE id = $1
            """,
            account_id,
            fetchrow=True,
        )

    async def get_account_user_by_identity(self, identity_id: int, account_id: int):
        return await self.execute(
            """
            SELECT
                au.*,
                a.name AS account_name,
                a.slug AS account_slug,
                a.status AS account_status,
                gi.full_name AS identity_full_name,
                gi.username AS identity_username
            FROM account_users au
            JOIN accounts a
              ON a.id = au.account_id
            LEFT JOIN global_identities gi
              ON gi.id = au.identity_id
            WHERE au.identity_id = $1
              AND au.account_id = $2
              AND au.status = 'active'
              AND a.status = 'active'
            ORDER BY au.id
            LIMIT 1
            """,
            identity_id,
            account_id,
            fetchrow=True,
        )

    async def get_account_user(self, telegram_id: int, account_id: int | None = None):
        if account_id is not None:
            return await self.execute(
                """
                SELECT
                    au.*,
                    a.name AS account_name,
                    a.slug AS account_slug,
                    a.status AS account_status,
                    gi.full_name AS identity_full_name,
                    gi.username AS identity_username
                FROM account_users au
                JOIN accounts a
                  ON a.id = au.account_id
                LEFT JOIN global_identities gi
                  ON gi.id = au.identity_id
                WHERE au.telegram_id = $1
                  AND au.account_id = $2
                ORDER BY au.id
                LIMIT 1
                """,
                telegram_id,
                account_id,
                fetchrow=True,
            )

        return await self.execute(
            """
            SELECT
                au.*,
                a.name AS account_name,
                a.slug AS account_slug,
                a.status AS account_status,
                gi.full_name AS identity_full_name,
                gi.username AS identity_username
            FROM account_users au
            JOIN accounts a
              ON a.id = au.account_id
            LEFT JOIN global_identities gi
              ON gi.id = au.identity_id
            WHERE au.telegram_id = $1
              AND au.status = 'active'
              AND a.status = 'active'
            ORDER BY
                CASE au.role
                    WHEN 'owner' THEN 1
                    WHEN 'manager' THEN 2
                    WHEN 'assistant' THEN 3
                    WHEN 'parent' THEN 4
                    ELSE 5
                END,
                au.account_id
            LIMIT 1
            """,
            telegram_id,
            fetchrow=True,
        )

    async def get_identity_memberships(
        self,
        telegram_id: int | None = None,
        identity_id: int | None = None,
    ) -> list:
        if identity_id is not None:
            return await self.execute(
                """
                SELECT
                    au.*,
                    a.name AS account_name,
                    a.slug AS account_slug,
                    a.status AS account_status,
                    gi.full_name AS identity_full_name,
                    gi.username AS identity_username,
                    gi.last_active_account_id
                FROM account_users au
                JOIN accounts a
                  ON a.id = au.account_id
                LEFT JOIN global_identities gi
                  ON gi.id = au.identity_id
                WHERE au.identity_id = $1
                  AND au.status = 'active'
                  AND a.status = 'active'
                ORDER BY
                    CASE
                        WHEN gi.last_active_account_id = au.account_id THEN 0
                        ELSE 1
                    END,
                    CASE au.role
                        WHEN 'owner' THEN 1
                        WHEN 'manager' THEN 2
                        WHEN 'assistant' THEN 3
                        WHEN 'parent' THEN 4
                        ELSE 5
                    END,
                    a.name,
                    au.account_id
                """,
                identity_id,
                fetch=True,
            )

        if telegram_id is None:
            return []

        return await self.execute(
            """
            SELECT
                au.*,
                a.name AS account_name,
                a.slug AS account_slug,
                a.status AS account_status,
                gi.full_name AS identity_full_name,
                gi.username AS identity_username,
                gi.last_active_account_id
            FROM account_users au
            JOIN accounts a
              ON a.id = au.account_id
            LEFT JOIN global_identities gi
              ON gi.id = au.identity_id
            WHERE au.telegram_id = $1
              AND au.status = 'active'
              AND a.status = 'active'
            ORDER BY
                CASE
                    WHEN gi.last_active_account_id = au.account_id THEN 0
                    ELSE 1
                END,
                CASE au.role
                    WHEN 'owner' THEN 1
                    WHEN 'manager' THEN 2
                    WHEN 'assistant' THEN 3
                    WHEN 'parent' THEN 4
                    ELSE 5
                END,
                a.name,
                au.account_id
            """,
            telegram_id,
            fetch=True,
        )

    async def resolve_account_context(self, telegram_id: int | None = None, invite_token: str | None = None) -> dict:
        invite = None
        account_user = None
        account = None
        identity = await self.get_global_identity(telegram_id) if telegram_id is not None else None

        if invite_token:
            invite = await self.get_account_invite_by_token(invite_token)
            if invite:
                account = await self.get_account_by_id(invite["account_id"])
                if telegram_id is not None:
                    if identity and identity.get("id"):
                        account_user = await self.get_account_user_by_identity(identity["id"], invite["account_id"])
                    if not account_user:
                        account_user = await self.get_account_user(telegram_id, invite["account_id"])

        if account is None and identity and identity.get("last_active_account_id"):
            account = await self.get_account_by_id(identity["last_active_account_id"])
            if account and account.get("status") == "active":
                account_user = await self.get_account_user_by_identity(identity["id"], account["id"])
                if not account_user:
                    account = None

        if account is None and telegram_id is not None:
            memberships = await self.get_identity_memberships(
                telegram_id=telegram_id,
                identity_id=identity["id"] if identity else None,
            )
            if memberships:
                account_user = memberships[0]
                account = await self.get_account_by_id(account_user["account_id"])

        if account is None:
            account = await self.get_default_account()

        return {
            "account": dict(account) if account else None,
            "account_user": dict(account_user) if account_user else None,
            "invite": dict(invite) if invite else None,
            "identity": dict(identity) if identity else None,
        }

    async def seed_default_plans(self):
        product = load_product_config()
        plans = product.get("plans", {})
        for order, code in enumerate(["start", "practice", "studio"], start=1):
            plan = plans.get(code, {})
            await self.execute(
                """
                INSERT INTO plans (code, sort_order, display_name, description, is_active)
                VALUES ($1, $2, $3, $4, true)
                ON CONFLICT (code) DO UPDATE
                SET sort_order = EXCLUDED.sort_order,
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    is_active = true
                """,
                code,
                order,
                plan.get("display_name", code.title()),
                plan.get("summary", ""),
                execute=True,
            )

    async def ensure_default_account(self) -> int:
        existing = await self.execute(
            """
            SELECT *
            FROM accounts
            WHERE is_default = true
            ORDER BY id
            LIMIT 1
            """,
            fetchrow=True,
        )
        if existing:
            self.account_id = existing["id"]
            return int(existing["id"])

        account_id = await self.execute(
            """
            INSERT INTO accounts (code, name, slug, status, is_default)
            VALUES ('default', $1, 'default', 'active', true)
            RETURNING id
            """,
            get_product_name(),
            fetchval=True,
        )
        self.account_id = account_id
        return int(account_id)

    async def ensure_default_subscription(self):
        account_id = self.require_account_id()
        trial_plan, trial_ends_at = build_default_trial_window()
        await self.execute(
            """
            INSERT INTO subscriptions (
                account_id,
                plan_code,
                status,
                trial_started_at,
                trial_ends_at,
                created_at,
                updated_at
            )
            VALUES ($1, $2, 'trial', CURRENT_TIMESTAMP, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (account_id) DO NOTHING
            """,
            account_id,
            trial_plan,
            trial_ends_at,
            execute=True,
        )

    async def get_account(self):
        return await self.execute(
            "SELECT * FROM accounts WHERE id = $1",
            self.require_account_id(),
            fetchrow=True,
        )

    async def get_account_owner_user(self):
        account = await self.get_account()
        owner_user_id = account["owner_user_id"] if account else None
        if not owner_user_id:
            return None
        return await self.get_user(owner_user_id)

    async def set_account_owner(self, telegram_id: int):
        await self.execute(
            """
            UPDATE accounts
            SET owner_user_id = $2,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            self.require_account_id(),
            telegram_id,
            execute=True,
        )

    async def ensure_account_user(self, telegram_id: int, role: str):
        role = self._normalize_account_role(role)
        account_id = self.require_account_id()
        await self.ensure_team_member_capacity(role, telegram_id=telegram_id, account_id=account_id)
        identity = await self.ensure_global_identity(telegram_id)
        identity_id = identity["id"] if identity else None
        await self.execute(
            """
            INSERT INTO account_users (account_id, identity_id, telegram_id, role, status)
            VALUES ($1, $2, $3, $4, 'active')
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = COALESCE(EXCLUDED.identity_id, account_users.identity_id),
                role = EXCLUDED.role,
                status = 'active',
                updated_at = CURRENT_TIMESTAMP
            """,
            account_id,
            identity_id,
            telegram_id,
            role,
            execute=True,
        )
        await self.set_last_active_account(telegram_id, account_id, identity_id=identity_id)
        if role == "owner":
            await self.set_account_owner(telegram_id)

    async def upsert_account_identity_user(
        self,
        telegram_id: int,
        full_name: str,
        username: str | None,
        role: str,
    ):
        identity = await self.ensure_global_identity(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
        )
        await self.execute(
            """
            INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = EXCLUDED.identity_id,
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                is_active = true
            """,
            self.require_account_id(),
            identity["id"] if identity else None,
            telegram_id,
            full_name,
            username,
            role,
            execute=True,
        )
        await self.ensure_account_user(telegram_id, role)

    async def get_subscription_record(self):
        row = await self.execute(
            """
            SELECT s.*, p.display_name AS plan_display_name, p.description AS plan_description
            FROM subscriptions s
            JOIN plans p ON p.code = s.plan_code
            WHERE s.account_id = $1
            """,
            self.require_account_id(),
            fetchrow=True,
        )
        return dict(row) if row else None

    async def get_feature_override_rows(self):
        return await self.execute(
            """
            SELECT capability, is_enabled
            FROM account_feature_overrides
            WHERE account_id = $1
            ORDER BY capability
            """,
            self.require_account_id(),
            fetch=True,
        )

    async def get_feature_overrides(self) -> dict[str, bool]:
        rows = await self.get_feature_override_rows()
        return {row["capability"]: bool(row["is_enabled"]) for row in rows}

    async def _get_ui_config_record(self, account_id: int):
        return await self.execute(
            """
            SELECT *
            FROM account_ui_configs
            WHERE account_id = $1
            """,
            account_id,
            fetchrow=True,
        )

    async def _get_ui_version_record(self, account_id: int, version: int):
        return await self.execute(
            """
            SELECT *
            FROM account_ui_versions
            WHERE account_id = $1
              AND version = $2
            """,
            account_id,
            version,
            fetchrow=True,
        )

    def _build_ui_snapshot(self, account: dict | None, record, defaults: dict, *, resolved_payload: dict) -> dict:
        draft_payload = _normalize_ui_payload(record["draft_payload"], defaults) if record else deepcopy(defaults)
        published_payload = _normalize_ui_payload(record["published_payload"], defaults) if record else deepcopy(defaults)
        return {
            "account": dict(account) if account else {},
            "defaults": deepcopy(defaults),
            "draft": draft_payload,
            "published": published_payload,
            "resolved": _normalize_ui_payload(resolved_payload, defaults),
            "draft_version": int(record["draft_version"]) if record and record.get("draft_version") is not None else 1,
            "published_version": int(record["published_version"]) if record and record.get("published_version") is not None else 1,
            "updated_by": record["updated_by"] if record else None,
            "published_by": record["published_by"] if record else None,
            "updated_at": record["updated_at"] if record else None,
            "published_at": record["published_at"] if record else None,
            "source": "database" if record else "defaults",
        }

    async def get_resolved_ui_config(self, account_id: int):
        defaults = load_ui_seed_defaults()
        account = await self.get_account_by_id(account_id)
        record = await self._get_ui_config_record(account_id)
        if not record:
            return self._build_ui_snapshot(account, None, defaults, resolved_payload=defaults)
        published = _normalize_ui_payload(record["published_payload"], defaults)
        return self._build_ui_snapshot(account, record, defaults, resolved_payload=published)

    async def get_ui_draft(self, account_id: int):
        defaults = load_ui_seed_defaults()
        account = await self.get_account_by_id(account_id)
        record = await self._get_ui_config_record(account_id)
        if not record:
            return self._build_ui_snapshot(account, None, defaults, resolved_payload=defaults)
        draft = _normalize_ui_payload(record["draft_payload"], defaults)
        return self._build_ui_snapshot(account, record, defaults, resolved_payload=draft)

    async def _ensure_ui_config_record(self, account_id: int):
        defaults = load_ui_seed_defaults()
        defaults_json = json.dumps(defaults, ensure_ascii=False)
        await self.execute(
            """
            INSERT INTO account_ui_configs (
                account_id,
                draft_payload,
                published_payload,
                draft_version,
                published_version,
                updated_at,
                published_at,
                created_at
            )
            VALUES (
                $1,
                $2::jsonb,
                $2::jsonb,
                1,
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (account_id) DO UPDATE
            SET draft_payload = CASE
                    WHEN account_ui_configs.draft_payload = '{}'::jsonb THEN EXCLUDED.draft_payload
                    ELSE account_ui_configs.draft_payload
                END,
                published_payload = CASE
                    WHEN account_ui_configs.published_payload = '{}'::jsonb THEN EXCLUDED.published_payload
                    ELSE account_ui_configs.published_payload
                END,
                draft_version = CASE
                    WHEN account_ui_configs.draft_payload = '{}'::jsonb
                     AND account_ui_configs.published_payload = '{}'::jsonb
                    THEN 1
                    ELSE account_ui_configs.draft_version
                END,
                published_version = CASE
                    WHEN account_ui_configs.draft_payload = '{}'::jsonb
                     AND account_ui_configs.published_payload = '{}'::jsonb
                    THEN 1
                    ELSE account_ui_configs.published_version
                END,
                published_at = CASE
                    WHEN account_ui_configs.published_payload = '{}'::jsonb
                    THEN CURRENT_TIMESTAMP
                    ELSE account_ui_configs.published_at
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            account_id,
            defaults_json,
            execute=True,
        )
        await self.execute(
            """
            INSERT INTO account_ui_versions (
                account_id,
                version,
                payload,
                published_by,
                published_at,
                created_at
            )
            VALUES ($1, 1, $2::jsonb, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (account_id, version) DO NOTHING
            """,
            account_id,
            defaults_json,
            execute=True,
        )

    async def save_ui_draft(self, account_id: int, payload: dict, updated_by: int | None):
        defaults = load_ui_seed_defaults()
        await self._ensure_ui_config_record(account_id)
        record = await self._get_ui_config_record(account_id)
        current = _normalize_ui_payload(record["draft_payload"], defaults) if record else deepcopy(defaults)
        draft_version = int(record["draft_version"] or record["published_version"] or 1) + 1 if record else 2
        published_version = int(record["published_version"] or 1) if record else 1

        merged = _normalize_ui_payload(_deep_merge(current, payload), defaults)
        payload_json = json.dumps(merged, ensure_ascii=False)

        await self.execute(
            """
            INSERT INTO account_ui_configs (
                account_id,
                draft_payload,
                published_payload,
                draft_version,
                published_version,
                updated_by,
                updated_at,
                published_at,
                created_at
            )
            VALUES (
                $1,
                $2::jsonb,
                $3::jsonb,
                $4,
                $5,
                $6,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (account_id) DO UPDATE
            SET draft_payload = EXCLUDED.draft_payload,
                draft_version = EXCLUDED.draft_version,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            account_id,
            payload_json,
            json.dumps(_normalize_ui_payload(record["published_payload"], defaults), ensure_ascii=False) if record else json.dumps(defaults, ensure_ascii=False),
            draft_version,
            published_version,
            updated_by,
            execute=True,
        )
        return await self.get_ui_draft(account_id)

    async def publish_ui_draft(self, account_id: int, published_by: int | None):
        defaults = load_ui_seed_defaults()
        await self._ensure_ui_config_record(account_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow(
                    """
                    SELECT *
                    FROM account_ui_configs
                    WHERE account_id = $1
                    FOR UPDATE
                    """,
                    account_id,
                )
                if not record:
                    raise RuntimeError("UI config record could not be initialized.")

                current_draft = _normalize_ui_payload(record["draft_payload"], defaults)
                current_published_version = int(record["published_version"] or 1)
                new_version = current_published_version + 1
                payload_json = json.dumps(current_draft, ensure_ascii=False)
                await conn.execute(
                    """
                    INSERT INTO account_ui_versions (
                        account_id,
                        version,
                        payload,
                        published_by,
                        published_at,
                        created_at
                    )
                    VALUES ($1, $2, $3::jsonb, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    account_id,
                    new_version,
                    payload_json,
                    published_by,
                )
                await conn.execute(
                    """
                    UPDATE account_ui_configs
                    SET published_payload = $2::jsonb,
                        published_version = $3,
                        published_by = $4,
                        published_at = CURRENT_TIMESTAMP,
                        updated_by = COALESCE($4, updated_by),
                        draft_version = GREATEST(draft_version, $3),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = $1
                    """,
                    account_id,
                    payload_json,
                    new_version,
                    published_by,
                )
        return await self.get_resolved_ui_config(account_id)

    async def list_ui_versions(self, account_id: int):
        defaults = load_ui_seed_defaults()
        rows = await self.execute(
            """
            SELECT *
            FROM account_ui_versions
            WHERE account_id = $1
            ORDER BY version DESC, id DESC
            """,
            account_id,
            fetch=True,
        )
        result = []
        for row in rows:
            payload = _normalize_ui_payload(row["payload"], defaults)
            result.append({
                "id": row["id"],
                "account_id": row["account_id"],
                "version": row["version"],
                "payload": payload,
                "published_by": row["published_by"],
                "published_at": row["published_at"],
                "created_at": row["created_at"],
            })
        return result

    async def rollback_ui_version(self, account_id: int, version: int, actor_id: int | None):
        defaults = load_ui_seed_defaults()
        await self._ensure_ui_config_record(account_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    """
                    SELECT *
                    FROM account_ui_configs
                    WHERE account_id = $1
                    FOR UPDATE
                    """,
                    account_id,
                )
                target = await conn.fetchrow(
                    """
                    SELECT *
                    FROM account_ui_versions
                    WHERE account_id = $1
                      AND version = $2
                    """,
                    account_id,
                    version,
                )
                if not current:
                    raise RuntimeError("UI config record could not be initialized.")
                if not target:
                    raise ValueError(f"UI version {version} not found for account {account_id}.")

                payload = _normalize_ui_payload(target["payload"], defaults)
                payload_json = json.dumps(payload, ensure_ascii=False)
                new_version = int(current["published_version"] or 1) + 1
                await conn.execute(
                    """
                    INSERT INTO account_ui_versions (
                        account_id,
                        version,
                        payload,
                        published_by,
                        published_at,
                        created_at
                    )
                    VALUES ($1, $2, $3::jsonb, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    account_id,
                    new_version,
                    payload_json,
                    actor_id,
                )
                await conn.execute(
                    """
                    UPDATE account_ui_configs
                    SET draft_payload = $2::jsonb,
                        published_payload = $2::jsonb,
                        draft_version = GREATEST(draft_version, $3),
                        published_version = $3,
                        updated_by = COALESCE($4, updated_by),
                        published_by = $4,
                        published_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = $1
                    """,
                    account_id,
                    payload_json,
                    new_version,
                    actor_id,
                )
        return await self.get_resolved_ui_config(account_id)

    async def get_account_billing_snapshot(self) -> dict:
        subscription = await self.get_subscription_record()
        overrides = await self.get_feature_overrides()
        account = await self.get_account()
        resolved = resolve_subscription(subscription, overrides=overrides)
        product = load_product_config()
        return {
            "account": dict(account) if account else {},
            "subscription": dict(subscription) if subscription else {},
            "resolved": resolved,
            "product": product,
            "configured_plan": product.get("plans", {}).get(resolved.plan_code, {}),
            "effective_plan": product.get("plans", {}).get(resolved.effective_plan_code, {}),
            "overrides": overrides,
            "locked_capabilities": resolved.locked_capabilities,
        }

    async def has_capability(self, capability: str) -> bool:
        snapshot = await self.get_account_billing_snapshot()
        return bool(snapshot["resolved"].capabilities.get(capability, False))

    async def activate_paid_subscription(
        self,
        plan_code: str,
        days: int,
        activated_by: int | None = None,
        notes: str = "",
    ):
        now = datetime.now()
        current = await self.get_subscription_record()
        base = current["paid_until"] if current and current["paid_until"] and current["paid_until"] > now else now
        paid_until = base + timedelta(days=max(int(days), 1))
        plan_code = normalize_plan_code(plan_code)
        await self.execute(
            """
            INSERT INTO subscriptions (
                account_id,
                plan_code,
                status,
                trial_started_at,
                trial_ends_at,
                paid_until,
                activated_by,
                notes,
                created_at,
                updated_at
            )
            VALUES ($1, $2, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (account_id) DO UPDATE
            SET plan_code = EXCLUDED.plan_code,
                status = 'active',
                paid_until = EXCLUDED.paid_until,
                activated_by = EXCLUDED.activated_by,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            self.require_account_id(),
            plan_code,
            paid_until,
            activated_by,
            notes,
            execute=True,
        )

    async def extend_trial(self, days: int, activated_by: int | None = None):
        now = datetime.now()
        current = await self.get_subscription_record()
        trial_plan, _ = build_default_trial_window(now=now)
        plan_code = normalize_plan_code(current["plan_code"] if current else trial_plan)
        base = current["trial_ends_at"] if current and current["trial_ends_at"] and current["trial_ends_at"] > now else now
        trial_ends_at = base + timedelta(days=max(int(days), 1))
        await self.execute(
            """
            INSERT INTO subscriptions (
                account_id,
                plan_code,
                status,
                trial_started_at,
                trial_ends_at,
                activated_by,
                created_at,
                updated_at
            )
            VALUES ($1, $2, 'trial', CURRENT_TIMESTAMP, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (account_id) DO UPDATE
            SET plan_code = EXCLUDED.plan_code,
                status = 'trial',
                trial_ends_at = EXCLUDED.trial_ends_at,
                activated_by = EXCLUDED.activated_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            self.require_account_id(),
            plan_code,
            trial_ends_at,
            activated_by,
            execute=True,
        )

    async def disable_trial(self, activated_by: int | None = None):
        current = await self.get_subscription_record()
        next_status = "active" if current and current["paid_until"] and current["paid_until"] >= datetime.now() else "inactive"
        await self.execute(
            """
            UPDATE subscriptions
            SET status = $2,
                trial_ends_at = CURRENT_TIMESTAMP,
                activated_by = COALESCE($3, activated_by),
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = $1
            """,
            self.require_account_id(),
            next_status,
            activated_by,
            execute=True,
        )

    async def toggle_feature_override(self, capability: str, updated_by: int | None = None) -> bool:
        existing = await self.execute(
            """
            SELECT id
            FROM account_feature_overrides
            WHERE account_id = $1
              AND capability = $2
            """,
            self.require_account_id(),
            capability,
            fetchrow=True,
        )
        if existing:
            await self.execute(
                "DELETE FROM account_feature_overrides WHERE id = $1",
                existing["id"],
                execute=True,
            )
            return False

        await self.execute(
            """
            INSERT INTO account_feature_overrides (account_id, capability, is_enabled, updated_by)
            VALUES ($1, $2, true, $3)
            """,
            self.require_account_id(),
            capability,
            updated_by,
            execute=True,
        )
        return True

    async def create_account_invite(
        self,
        role: str,
        created_by: int | None = None,
        label: str = "",
        days_valid: int = 7,
    ):
        role = self._normalize_account_role(role, invite_only=True)
        await self.ensure_team_member_capacity(
            role,
            account_id=self.require_account_id(),
            include_pending_invites=True,
        )
        token = token_urlsafe(16)
        expires_at = datetime.now() + timedelta(days=max(int(days_valid), 1))
        await self.execute(
            """
            INSERT INTO account_invites (account_id, token, role, label, status, created_by, expires_at)
            VALUES ($1, $2, $3, $4, 'active', $5, $6)
            """,
            self.require_account_id(),
            token,
            role,
            label,
            created_by,
            expires_at,
            execute=True,
        )
        invite = await self.get_account_invite_by_token(token, include_inactive=True)
        return dict(invite) if invite else None

    async def get_active_account_invites(self):
        return await self.execute(
            """
            SELECT *
            FROM account_invites
            WHERE account_id = $1
              AND status = 'active'
              AND redeemed_at IS NULL
              AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
            ORDER BY created_at DESC, id DESC
            """,
            self.require_account_id(),
            fetch=True,
        )

    async def get_account_invite_by_token(self, token: str, include_inactive: bool = False):
        if include_inactive:
            return await self.execute(
                """
                SELECT ai.*, a.name AS account_name, a.slug AS account_slug
                FROM account_invites ai
                JOIN accounts a
                  ON a.id = ai.account_id
                WHERE ai.token = $1
                ORDER BY ai.id DESC
                LIMIT 1
                """,
                token,
                fetchrow=True,
            )

        return await self.execute(
            """
            SELECT ai.*, a.name AS account_name, a.slug AS account_slug
            FROM account_invites ai
            JOIN accounts a
              ON a.id = ai.account_id
            WHERE ai.token = $1
              AND ai.status = 'active'
              AND ai.redeemed_at IS NULL
              AND (ai.expires_at IS NULL OR ai.expires_at >= CURRENT_TIMESTAMP)
            ORDER BY ai.id DESC
            LIMIT 1
            """,
            token,
            fetchrow=True,
        )

    async def redeem_account_invite(
        self,
        token: str,
        telegram_id: int,
        full_name: str = "",
        username: str | None = None,
    ):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                invite = await conn.fetchrow(
                    """
                    SELECT *
                    FROM account_invites
                    WHERE token = $1
                      AND status = 'active'
                      AND redeemed_at IS NULL
                      AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
                    FOR UPDATE
                    """,
                    token,
                )
                if not invite:
                    return None
                invite_role = self._normalize_account_role(invite["role"], invite_only=True)
                await self.ensure_team_member_capacity(
                    invite_role,
                    telegram_id=telegram_id,
                    account_id=invite["account_id"],
                    connection=conn,
                )

                identity_id = await conn.fetchval(
                    """
                    INSERT INTO global_identities (
                        telegram_id,
                        full_name,
                        username,
                        status,
                        updated_at,
                        last_seen_at
                    )
                    VALUES ($1, $2, $3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), global_identities.full_name),
                        username = COALESCE(NULLIF(EXCLUDED.username, ''), global_identities.username),
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP,
                        last_seen_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    telegram_id,
                    full_name or "",
                    username or "",
                )
                await conn.execute(
                    """
                    INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (account_id, telegram_id) DO UPDATE
                    SET identity_id = EXCLUDED.identity_id,
                        full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name),
                        username = COALESCE(NULLIF(EXCLUDED.username, ''), users.username),
                        role = EXCLUDED.role,
                        is_active = true
                    """,
                    invite["account_id"],
                    identity_id,
                    telegram_id,
                    full_name or "",
                    username or "",
                    invite_role,
                )
                await conn.execute(
                    """
                    INSERT INTO account_users (account_id, identity_id, telegram_id, role, status)
                    VALUES ($1, $2, $3, $4, 'active')
                    ON CONFLICT (account_id, telegram_id) DO UPDATE
                    SET identity_id = EXCLUDED.identity_id,
                        role = EXCLUDED.role,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    invite["account_id"],
                    identity_id,
                    telegram_id,
                    invite_role,
                )
                await conn.execute(
                    """
                    UPDATE global_identities
                    SET last_active_account_id = $2,
                        updated_at = CURRENT_TIMESTAMP,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    identity_id,
                    invite["account_id"],
                )
                if invite_role == "owner":
                    await conn.execute(
                        """
                        UPDATE accounts
                        SET owner_user_id = $2,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                        """,
                        invite["account_id"],
                        telegram_id,
                    )
                await conn.execute(
                    """
                    UPDATE account_invites
                    SET status = 'redeemed',
                        redeemed_by = $2,
                        redeemed_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    invite["id"],
                    telegram_id,
                )

        account = await self.get_account_by_id(invite["account_id"])
        account_user = await self.get_account_user(telegram_id, invite["account_id"])
        return {
            "invite": dict(invite),
            "account": dict(account) if account else None,
            "account_user": dict(account_user) if account_user else None,
            "role_label": workspace_role_label(invite["role"]),
        }

    async def revoke_account_invite(self, invite_id: int):
        await self.execute(
            """
            UPDATE account_invites
            SET status = 'revoked'
            WHERE id = $1
              AND account_id = $2
              AND status = 'active'
            """,
            invite_id,
            self.require_account_id(),
            execute=True,
        )

    async def get_partition_health_snapshot(self):
        account_id = self.require_account_id()
        tables = [
            "users",
            "student_parent",
            "lessons",
            "homework",
            "payments",
            "calendar_student_links",
        ]
        snapshot = {
            "account_id": account_id,
            "tables": {},
            "healthy": True,
            "null_account_rows": 0,
        }
        for table_name in tables:
            total_rows = int(await self.execute(f"SELECT COUNT(*)::int FROM {table_name}", fetchval=True) or 0)
            null_rows = int(
                await self.execute(
                    f"SELECT COUNT(*)::int FROM {table_name} WHERE account_id IS NULL",
                    fetchval=True,
                ) or 0
            )
            account_rows = int(
                await self.execute(
                    f"SELECT COUNT(*)::int FROM {table_name} WHERE account_id = $1",
                    account_id,
                    fetchval=True,
                ) or 0
            )
            other_rows = max(total_rows - account_rows - null_rows, 0)
            snapshot["tables"][table_name] = {
                "total_rows": total_rows,
                "account_rows": account_rows,
                "null_account_rows": null_rows,
                "other_account_rows": other_rows,
            }
            snapshot["null_account_rows"] += null_rows
            if null_rows:
                snapshot["healthy"] = False
        return snapshot

    async def get_identity_split_snapshot(self):
        users_missing_identity = int(
            await self.execute(
                """
                SELECT COUNT(*)::int
                FROM users
                WHERE account_id = $1
                  AND identity_id IS NULL
                """,
                self.require_account_id(),
                fetchval=True,
            ) or 0
        )
        account_users_missing_identity = int(
            await self.execute(
                """
                SELECT COUNT(*)::int
                FROM account_users
                WHERE account_id = $1
                  AND identity_id IS NULL
                """,
                self.require_account_id(),
                fetchval=True,
            ) or 0
        )
        linked_users = int(
            await self.execute(
                """
                SELECT COUNT(*)::int
                FROM users
                WHERE account_id = $1
                  AND identity_id IS NOT NULL
                """,
                self.require_account_id(),
                fetchval=True,
            ) or 0
        )
        total_memberships = int(
            await self.execute(
                """
                SELECT COUNT(*)::int
                FROM account_users
                WHERE account_id = $1
                """,
                self.require_account_id(),
                fetchval=True,
            ) or 0
        )
        total_global_identities = int(
            await self.execute(
                "SELECT COUNT(*)::int FROM global_identities",
                fetchval=True,
            ) or 0
        )
        ready = users_missing_identity == 0 and account_users_missing_identity == 0
        return {
            "ready": ready,
            "users_missing_identity": users_missing_identity,
            "account_users_missing_identity": account_users_missing_identity,
            "linked_users": linked_users,
            "total_memberships": total_memberships,
            "total_global_identities": total_global_identities,
        }

    async def get_identity_workspace_snapshot(
        self,
        telegram_id: int | None = None,
        identity_id: int | None = None,
    ) -> dict:
        identity = None
        if identity_id is not None:
            identity = await self.get_global_identity_by_id(identity_id)
        elif telegram_id is not None:
            identity = await self.get_global_identity(telegram_id)
        memberships = await self.get_identity_memberships(
            telegram_id=telegram_id,
            identity_id=identity["id"] if identity else identity_id,
        )
        return {
            "identity": dict(identity) if identity else None,
            "memberships": [dict(item) for item in memberships],
        }

    async def get_account_team_members(self):
        return await self.execute(
            """
            SELECT
                au.id,
                au.account_id,
                au.identity_id,
                au.telegram_id,
                au.role,
                au.status,
                au.created_at,
                au.updated_at,
                COALESCE(u.full_name, gi.full_name, '@' || NULLIF(gi.username, '')) AS display_name,
                COALESCE(u.username, gi.username) AS username
            FROM account_users au
            LEFT JOIN users u
              ON u.account_id = au.account_id
             AND (u.identity_id = au.identity_id OR u.telegram_id = au.telegram_id)
            LEFT JOIN global_identities gi
              ON gi.id = au.identity_id
            WHERE au.account_id = $1
              AND au.status = 'active'
            ORDER BY
                CASE au.role
                    WHEN 'owner' THEN 1
                    WHEN 'manager' THEN 2
                    WHEN 'assistant' THEN 3
                    WHEN 'parent' THEN 4
                    ELSE 5
                END,
                COALESCE(u.full_name, gi.full_name, ''),
                au.id
            """,
            self.require_account_id(),
            fetch=True,
        )

    async def get_domain_user_ref_snapshot(self):
        account_id = self.require_account_id()
        checks = {
            "student_parent.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM student_parent
                WHERE account_id = $1
                  AND student_id IS NOT NULL
                  AND student_user_id IS NULL
                """,
                (account_id,),
            ),
            "student_parent.parent_user_id": (
                """
                SELECT COUNT(*)::int
                FROM student_parent
                WHERE account_id = $1
                  AND parent_id IS NOT NULL
                  AND parent_user_id IS NULL
                """,
                (account_id,),
            ),
            "lessons.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM lessons
                WHERE account_id = $1
                  AND student_id IS NOT NULL
                  AND student_user_id IS NULL
                """,
                (account_id,),
            ),
            "homework.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM homework
                WHERE account_id = $1
                  AND student_id IS NOT NULL
                  AND student_user_id IS NULL
                """,
                (account_id,),
            ),
            "payments.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM payments
                WHERE account_id = $1
                  AND student_id IS NOT NULL
                  AND student_user_id IS NULL
                """,
                (account_id,),
            ),
            "payments.payer_user_id": (
                """
                SELECT COUNT(*)::int
                FROM payments
                WHERE account_id = $1
                  AND payer_id IS NOT NULL
                  AND payer_user_id IS NULL
                """,
                (account_id,),
            ),
            "calendar_student_links.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM calendar_student_links
                WHERE account_id = $1
                  AND student_id IS NOT NULL
                  AND student_user_id IS NULL
                """,
                (account_id,),
            ),
            "group_members.student_user_id": (
                """
                SELECT COUNT(*)::int
                FROM group_members gm
                JOIN groups g
                  ON g.id = gm.group_id
                WHERE g.account_id = $1
                  AND gm.student_id IS NOT NULL
                  AND gm.student_user_id IS NULL
                """,
                (account_id,),
            ),
        }
        missing = {}
        total_missing = 0
        for key, (query, params) in checks.items():
            count = int(await self.execute(query, *params, fetchval=True) or 0)
            missing[key] = count
            total_missing += count
        return {
            "ready": total_missing == 0,
            "missing": missing,
            "total_missing": total_missing,
        }

    async def get_support_snapshot(self, operator_telegram_id: int | None = None):
        account = await self.get_account()
        billing = await self.get_account_billing_snapshot()
        analytics = await self.get_account_analytics_snapshot()
        invites = await self.get_active_account_invites()
        partition = await self.get_partition_health_snapshot()
        identity_split = await self.get_identity_split_snapshot()
        domain_user_refs = await self.get_domain_user_ref_snapshot()
        owner_user = await self.get_account_owner_user()
        identity_workspace = await self.get_identity_workspace_snapshot(telegram_id=operator_telegram_id)
        team_members = await self.get_account_team_members()
        active_members = await self.execute(
            """
            SELECT COUNT(*)::int
            FROM account_users
            WHERE account_id = $1
              AND status = 'active'
            """,
            self.require_account_id(),
            fetchval=True,
        )
        return {
            "account": dict(account) if account else {},
            "billing": billing,
            "analytics": dict(analytics or {}),
            "active_invites": [dict(item) for item in invites],
            "active_invites_count": len(invites or []),
            "partition": partition,
            "identity_split": identity_split,
            "domain_user_refs": domain_user_refs,
            "identity_workspace": identity_workspace,
            "team_members": [dict(item) for item in team_members],
            "owner_user": dict(owner_user) if owner_user else None,
            "active_members": int(active_members or 0),
        }

    async def get_groups_overview(self):
        return await self.execute(
            """
            SELECT
                g.id,
                g.name,
                g.description,
                COALESCE(COUNT(gm.id), 0)::int AS student_count
            FROM groups g
            LEFT JOIN group_members gm
              ON gm.group_id = g.id
            WHERE g.account_id = $1
              AND g.is_active = true
            GROUP BY g.id, g.name, g.description
            ORDER BY g.name
            """,
            self.require_account_id(),
            fetch=True,
        )

    async def get_group(self, group_id: int):
        return await self.execute(
            """
            SELECT *
            FROM groups
            WHERE id = $1
              AND account_id = $2
            """,
            group_id,
            self.require_account_id(),
            fetchrow=True,
        )

    async def get_group_members(self, group_id: int):
        return await self.execute(
            """
            SELECT u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal') AS speech_style
            FROM group_members gm
            JOIN groups g
              ON g.id = gm.group_id
            JOIN users u
              ON (
                    u.id = gm.student_user_id
                    OR (
                        gm.student_user_id IS NULL
                        AND u.telegram_id = gm.student_id
                    )
                 )
            WHERE gm.group_id = $1
              AND g.account_id = $2
              AND u.is_active = true
            ORDER BY u.full_name
            """,
            group_id,
            self.require_account_id(),
            fetch=True,
        )

    async def create_group(self, name: str, description: str = "") -> int:
        await self.ensure_group_capacity(account_id=self.require_account_id())
        return await self.execute(
            """
            INSERT INTO groups (account_id, name, description)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            self.require_account_id(),
            name,
            description,
            fetchval=True,
        )

    async def delete_group(self, group_id: int):
        await self.execute(
            """
            UPDATE groups
            SET is_active = false
            WHERE id = $1
              AND account_id = $2
            """,
            group_id,
            self.require_account_id(),
            execute=True,
        )

    async def add_student_to_group(self, group_id: int, student_id: int):
        student_user_id = await self.get_user_row_id(student_id)
        await self.execute(
            """
            INSERT INTO group_members (group_id, student_user_id, student_id)
            SELECT $1, $2, $3
            WHERE EXISTS (
                SELECT 1
                FROM groups g
                JOIN users u
                  ON u.id = $2
                WHERE g.id = $1
                  AND g.account_id = $4
                  AND u.account_id = $4
            )
            ON CONFLICT (group_id, student_id) DO NOTHING
            """,
            group_id,
            student_user_id,
            student_id,
            self.require_account_id(),
            execute=True,
        )

    async def remove_student_from_group(self, group_id: int, student_id: int):
        student_user_id = await self.get_user_row_id(student_id)
        await self.execute(
            """
            DELETE FROM group_members
            WHERE group_id = $1
              AND (student_id = $2 OR student_user_id = $3)
            """,
            group_id,
            student_id,
            student_user_id,
            execute=True,
        )

    async def get_broadcast_segment_students(self, segment: str, reference_now: datetime | None = None):
        account_id = self.require_account_id()
        current_local = reference_now or await self.get_account_now()
        if segment == "zero_balance":
            return await self.execute(
                """
                SELECT
                    u.telegram_id,
                    u.full_name,
                    COALESCE(u.speech_style, 'formal') AS speech_style
                FROM users u
                LEFT JOIN payments p
                  ON (p.student_user_id = u.id OR (p.student_user_id IS NULL AND p.student_id = u.telegram_id))
                 AND p.status = 'confirmed'
                 AND p.account_id = $1
                WHERE u.account_id = $1
                  AND u.role = 'student'
                  AND u.is_active = true
                  AND COALESCE(u.is_internal_account, false) = false
                GROUP BY u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal')
                HAVING COALESCE(SUM(p.lessons_remaining), 0) = 0
                ORDER BY u.full_name
                """,
                account_id,
                fetch=True,
            )
        if segment == "no_upcoming":
            return await self.execute(
                """
                SELECT
                    u.telegram_id,
                    u.full_name,
                    COALESCE(u.speech_style, 'formal') AS speech_style
                FROM users u
                WHERE u.account_id = $1
                  AND u.role = 'student'
                  AND u.is_active = true
                  AND COALESCE(u.is_internal_account, false) = false
                  AND NOT EXISTS (
                      SELECT 1
                      FROM lessons l
                      WHERE (l.student_user_id = u.id OR (l.student_user_id IS NULL AND l.student_id = u.telegram_id))
                        AND l.account_id = $1
                        AND l.status = 'active'
                        AND l.lesson_date IS NOT NULL
                        AND l.lesson_date >= $2
                  )
                ORDER BY u.full_name
                """,
                account_id,
                current_local,
                fetch=True,
            )
        if segment == "with_parents":
            return await self.execute(
                """
                SELECT DISTINCT
                    u.telegram_id,
                    u.full_name,
                    COALESCE(u.speech_style, 'formal') AS speech_style
                FROM users u
                JOIN student_parent sp
                  ON (sp.student_user_id = u.id OR (sp.student_user_id IS NULL AND sp.student_id = u.telegram_id))
                 AND sp.account_id = $1
                 AND sp.is_active = true
                WHERE u.account_id = $1
                  AND u.role = 'student'
                  AND u.is_active = true
                  AND COALESCE(u.is_internal_account, false) = false
                ORDER BY u.full_name
                """,
                account_id,
                fetch=True,
            )
        return await self.execute(
            """
            SELECT telegram_id, full_name, COALESCE(speech_style, 'formal') AS speech_style
            FROM users
            WHERE account_id = $1
              AND role = 'student'
              AND is_active = true
              AND COALESCE(is_internal_account, false) = false
            ORDER BY full_name
            """,
            account_id,
            fetch=True,
        )

    async def get_account_analytics_snapshot(self, reference_now: datetime | None = None):
        account_id = self.require_account_id()
        current_local = reference_now or await self.get_account_now()
        next_week = current_local + timedelta(days=7)
        last_30_days = current_local - timedelta(days=30)
        return await self.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.account_id = $1
                      AND u.role = 'student'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS active_students,
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.account_id = $1
                      AND u.role = 'parent'
                      AND u.is_active = true
                ) AS active_parents,
                (
                    SELECT COUNT(*)::int
                    FROM groups g
                    WHERE g.account_id = $1
                      AND g.is_active = true
                ) AS active_groups,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    WHERE l.account_id = $1
                      AND l.status = 'active'
                      AND l.lesson_date >= $2
                      AND l.lesson_date < $3
                ) AS lessons_next_7_days,
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.account_id = $1
                      AND u.role = 'student'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                      AND NOT EXISTS (
                          SELECT 1
                          FROM lessons l
                          WHERE l.account_id = $1
                            AND (l.student_user_id = u.id OR (l.student_user_id IS NULL AND l.student_id = u.telegram_id))
                            AND l.status = 'active'
                            AND l.lesson_date >= $2
                      )
                ) AS students_without_upcoming_lessons,
                (
                    SELECT COALESCE(SUM(p.amount), 0)
                    FROM payments p
                    WHERE p.account_id = $1
                      AND p.status = 'confirmed'
                      AND p.created_at >= $4
                ) AS revenue_last_30_days,
                (
                    SELECT COUNT(*)::int
                    FROM payments p
                    WHERE p.account_id = $1
                      AND p.status = 'confirmed'
                      AND p.created_at >= $4
                ) AS payments_last_30_days,
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.account_id = $1
                      AND u.role = 'student'
                      AND u.is_active = true
                      AND COALESCE(u.lesson_format, 'online') = 'offline'
                ) AS offline_students,
                (
                    SELECT COUNT(*)::int
                    FROM calendar_student_links csl
                    WHERE csl.account_id = $1
                      AND csl.is_active = true
                ) AS calendar_alias_rules
            """,
            account_id,
            current_local,
            next_week,
            last_30_days,
            fetchrow=True,
        )
