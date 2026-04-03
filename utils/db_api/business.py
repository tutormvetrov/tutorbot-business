from __future__ import annotations

from datetime import datetime, timedelta
from secrets import token_urlsafe

from data.config import get_product_name, load_product_config
from utils.capabilities import build_default_trial_window, normalize_plan_code, resolve_subscription
from utils.workspace import workspace_role_label


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

    async def resolve_account_context(self, telegram_id: int | None = None, invite_token: str | None = None) -> dict:
        invite = None
        account_user = None
        account = None

        if invite_token:
            invite = await self.get_account_invite_by_token(invite_token)
            if invite:
                account = await self.get_account_by_id(invite["account_id"])
                if telegram_id is not None:
                    account_user = await self.get_account_user(telegram_id, invite["account_id"])

        if account is None and telegram_id is not None:
            account_user = await self.get_account_user(telegram_id)
            if account_user:
                account = await self.get_account_by_id(account_user["account_id"])

        if account is None and telegram_id is not None:
            user_account = await self.execute(
                """
                SELECT account_id
                FROM users
                WHERE telegram_id = $1
                  AND account_id IS NOT NULL
                ORDER BY account_id
                LIMIT 1
                """,
                telegram_id,
                fetchrow=True,
            )
            if user_account:
                account = await self.get_account_by_id(user_account["account_id"])
                account_user = await self.get_account_user(telegram_id, user_account["account_id"])

        if account is None:
            account = await self.get_default_account()

        identity = await self.get_global_identity(telegram_id) if telegram_id is not None else None

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
        account_id = self.require_account_id()
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
            ON CONFLICT (telegram_id) DO UPDATE
            SET account_id = EXCLUDED.account_id,
                identity_id = EXCLUDED.identity_id,
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
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET account_id = EXCLUDED.account_id,
                        identity_id = EXCLUDED.identity_id,
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
                    invite["role"],
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
                    invite["role"],
                )
                if invite["role"] == "owner":
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

    async def get_support_snapshot(self):
        account = await self.get_account()
        billing = await self.get_account_billing_snapshot()
        analytics = await self.get_account_analytics_snapshot()
        invites = await self.get_active_account_invites()
        partition = await self.get_partition_health_snapshot()
        identity_split = await self.get_identity_split_snapshot()
        domain_user_refs = await self.get_domain_user_ref_snapshot()
        owner_user = await self.get_account_owner_user()
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

    async def get_broadcast_segment_students(self, segment: str):
        account_id = self.require_account_id()
        if segment == "zero_balance":
            return await self.execute(
                """
                SELECT
                    u.telegram_id,
                    u.full_name,
                    COALESCE(u.speech_style, 'formal') AS speech_style
                FROM users u
                LEFT JOIN payments p
                  ON p.student_id = u.telegram_id
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
                      WHERE l.student_id = u.telegram_id
                        AND l.account_id = $1
                        AND l.status = 'active'
                        AND l.lesson_date IS NOT NULL
                        AND l.lesson_date >= NOW()
                  )
                ORDER BY u.full_name
                """,
                account_id,
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
                  ON sp.student_id = u.telegram_id
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

    async def get_account_analytics_snapshot(self):
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
                      AND l.lesson_date >= NOW()
                      AND l.lesson_date < NOW() + INTERVAL '7 days'
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
                            AND l.student_id = u.telegram_id
                            AND l.status = 'active'
                            AND l.lesson_date >= NOW()
                      )
                ) AS students_without_upcoming_lessons,
                (
                    SELECT COALESCE(SUM(p.amount), 0)
                    FROM payments p
                    WHERE p.account_id = $1
                      AND p.status = 'confirmed'
                      AND p.created_at >= NOW() - INTERVAL '30 days'
                ) AS revenue_last_30_days,
                (
                    SELECT COUNT(*)::int
                    FROM payments p
                    WHERE p.account_id = $1
                      AND p.status = 'confirmed'
                      AND p.created_at >= NOW() - INTERVAL '30 days'
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
            self.require_account_id(),
            fetchrow=True,
        )
