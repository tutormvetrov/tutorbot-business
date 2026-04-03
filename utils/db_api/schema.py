import logging


logger = logging.getLogger(__name__)


class DatabaseSchemaMixin:
    def _log_migration_failure(self, migration_name: str, exc: Exception):
        logger.error("Schema migration failed: %s: %s", migration_name, exc)

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    async def create_table_global_identities(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS global_identities (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                full_name VARCHAR(255),
                username VARCHAR(255),
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_accounts(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                owner_user_id BIGINT,
                is_default BOOLEAN DEFAULT false,
                timezone TEXT DEFAULT 'Europe/Moscow',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_users(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                identity_id INTEGER REFERENCES global_identities(id),
                telegram_id BIGINT NOT NULL,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255),
                role VARCHAR(50) NOT NULL,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT true
            );
        """, execute=True)

    async def create_table_student_parent(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_parent (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                student_user_id INTEGER REFERENCES users(id),
                parent_user_id INTEGER REFERENCES users(id),
                student_id BIGINT,
                parent_id BIGINT,
                student_info TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_lessons(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                student_user_id INTEGER REFERENCES users(id),
                student_id BIGINT,
                google_event_id TEXT,
                lesson_date TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                freeze_start_date TIMESTAMP,
                freeze_end_date TIMESTAMP,
                freeze_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_homework(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                student_user_id INTEGER REFERENCES users(id),
                student_id BIGINT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                deadline TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                reminder_sent BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_payments(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                payer_user_id INTEGER REFERENCES users(id),
                student_user_id INTEGER REFERENCES users(id),
                payer_id BIGINT,
                student_id BIGINT,
                amount DECIMAL(10,2) NOT NULL,
                lessons_count INTEGER NOT NULL,
                lessons_remaining INTEGER NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                payment_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_calendar_student_links(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS calendar_student_links (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                student_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                student_id BIGINT NOT NULL,
                calendar_alias TEXT,
                calendar_event_pattern TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT calendar_student_links_match_check
                    CHECK (
                        COALESCE(NULLIF(BTRIM(calendar_alias), ''), NULL) IS NOT NULL
                        OR COALESCE(NULLIF(BTRIM(calendar_event_pattern), ''), NULL) IS NOT NULL
                    )
            );
        """, execute=True)

    async def create_table_account_users(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS account_users (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                identity_id INTEGER REFERENCES global_identities(id) ON DELETE SET NULL,
                telegram_id BIGINT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (account_id, telegram_id)
            );
        """, execute=True)

    async def create_table_plans(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                code TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_subscriptions(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                plan_code TEXT NOT NULL REFERENCES plans(code),
                status TEXT NOT NULL DEFAULT 'trial',
                trial_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_ends_at TIMESTAMP,
                paid_until TIMESTAMP,
                activated_by BIGINT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_account_feature_overrides(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS account_feature_overrides (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                capability TEXT NOT NULL,
                is_enabled BOOLEAN NOT NULL DEFAULT true,
                updated_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (account_id, capability)
            );
        """, execute=True)

    async def create_table_account_invites(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS account_invites (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                label TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_by BIGINT,
                redeemed_by BIGINT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                redeemed_at TIMESTAMP
            );
        """, execute=True)

    async def create_table_groups(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_group_members(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                id SERIAL PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                student_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                student_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (group_id, student_id)
            );
        """, execute=True)

    async def migrate_lessons_google_event_id(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ALTER COLUMN google_event_id DROP NOT NULL;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_google_event_id", exc)
            return

    async def migrate_lessons_add_date(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS lesson_date TIMESTAMP;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_date", exc)
            return

    async def migrate_lessons_google_event_id_unique(self):
        try:
            index_def = await self.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'lessons'
                  AND indexname = 'lessons_google_event_id_idx'
                """,
                fetchval=True,
            )
            if index_def and " WHERE " in index_def.upper():
                await self.execute(
                    "DROP INDEX IF EXISTS lessons_google_event_id_idx;",
                    execute=True,
                )
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS lessons_google_event_id_idx
                ON lessons (google_event_id);
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_google_event_id_unique", exc)
            return

    async def migrate_lessons_add_reminder_sent(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_reminder_sent", exc)
            return

    async def migrate_users_add_language_level(self):
        for col, definition in [
            ("language", "TEXT"),
            ("level", "TEXT"),
            ("age", "INTEGER"),
            ("review_sent", "BOOLEAN DEFAULT false"),
            ("lesson_reminders", "TEXT DEFAULT 'enabled'"),
            ("is_internal_account", "BOOLEAN DEFAULT false"),
        ]:
            try:
                await self.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition};",
                    execute=True,
                )
            except Exception as exc:
                self._log_migration_failure(f"migrate_users_add_language_level:{col}", exc)
                return

    async def migrate_users_add_lesson_format(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS lesson_format TEXT DEFAULT 'online';",
                execute=True,
            )
            await self.execute(
                "UPDATE users SET lesson_format = 'online' WHERE lesson_format IS NULL OR lesson_format = '';",
                execute=True,
            )
            await self.execute(
                """
                UPDATE users
                SET lesson_format = 'offline'
                WHERE role = 'student'
                  AND LOWER(BTRIM(full_name)) IN ('мария вовк', 'георгий мартынов');
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_lesson_format", exc)
            return

    async def migrate_identity_split_columns(self):
        statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_id INTEGER REFERENCES global_identities(id);",
            "ALTER TABLE account_users ADD COLUMN IF NOT EXISTS identity_id INTEGER REFERENCES global_identities(id);",
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"migrate_identity_split_columns:{index}", exc)
                return

    async def migrate_identity_split_indexes(self):
        statements = [
            """
            CREATE UNIQUE INDEX IF NOT EXISTS account_users_account_identity_unique_idx
            ON account_users (account_id, identity_id)
            WHERE identity_id IS NOT NULL;
            """,
            """
            CREATE INDEX IF NOT EXISTS users_identity_id_idx
            ON users (identity_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS account_users_identity_id_idx
            ON account_users (identity_id);
            """,
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"migrate_identity_split_indexes:{index}", exc)
                return

    async def migrate_users_account_scoped_unique_index(self):
        try:
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS users_account_telegram_unique_idx
                ON users (account_id, telegram_id);
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_account_scoped_unique_index", exc)
            return

    async def migrate_drop_legacy_user_telegram_foreign_keys(self):
        legacy_fk_columns = [
            ("student_parent", "student_id"),
            ("student_parent", "parent_id"),
            ("lessons", "student_id"),
            ("homework", "student_id"),
            ("payments", "payer_id"),
            ("payments", "student_id"),
            ("calendar_student_links", "student_id"),
            ("account_users", "telegram_id"),
            ("group_members", "student_id"),
        ]
        for index, (table_name, column_name) in enumerate(legacy_fk_columns, start=1):
            try:
                constraints = await self.execute(
                    """
                    SELECT DISTINCT c.conname
                    FROM pg_constraint c
                    JOIN pg_class tbl
                      ON tbl.oid = c.conrelid
                    JOIN pg_namespace ns
                      ON ns.oid = tbl.relnamespace
                    JOIN pg_attribute attr
                      ON attr.attrelid = tbl.oid
                     AND attr.attnum = ANY(c.conkey)
                    JOIN pg_class ref_tbl
                      ON ref_tbl.oid = c.confrelid
                    WHERE c.contype = 'f'
                      AND ns.nspname = current_schema()
                      AND tbl.relname = $1
                      AND attr.attname = $2
                      AND ref_tbl.relname = 'users'
                    """,
                    table_name,
                    column_name,
                    fetch=True,
                )
                for row in constraints:
                    quoted_table = self._quote_identifier(table_name)
                    quoted_constraint = self._quote_identifier(row["conname"])
                    await self.execute(
                        f"ALTER TABLE {quoted_table} DROP CONSTRAINT IF EXISTS {quoted_constraint};",
                        execute=True,
                    )
            except Exception as exc:
                self._log_migration_failure(
                    f"migrate_drop_legacy_user_telegram_foreign_keys:{index}",
                    exc,
                )
                return

    async def migrate_domain_user_ref_columns(self):
        statements = [
            "ALTER TABLE student_parent ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE student_parent ADD COLUMN IF NOT EXISTS parent_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE homework ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payer_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE calendar_student_links ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
            "ALTER TABLE group_members ADD COLUMN IF NOT EXISTS student_user_id INTEGER REFERENCES users(id);",
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"migrate_domain_user_ref_columns:{index}", exc)
                return

    async def migrate_domain_user_ref_indexes(self):
        statements = [
            "CREATE INDEX IF NOT EXISTS student_parent_student_user_id_idx ON student_parent (student_user_id);",
            "CREATE INDEX IF NOT EXISTS student_parent_parent_user_id_idx ON student_parent (parent_user_id);",
            "CREATE INDEX IF NOT EXISTS lessons_student_user_id_idx ON lessons (student_user_id);",
            "CREATE INDEX IF NOT EXISTS homework_student_user_id_idx ON homework (student_user_id);",
            "CREATE INDEX IF NOT EXISTS payments_student_user_id_idx ON payments (student_user_id);",
            "CREATE INDEX IF NOT EXISTS payments_payer_user_id_idx ON payments (payer_user_id);",
            "CREATE INDEX IF NOT EXISTS calendar_student_links_student_user_id_idx ON calendar_student_links (student_user_id);",
            "CREATE INDEX IF NOT EXISTS group_members_student_user_id_idx ON group_members (student_user_id);",
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"migrate_domain_user_ref_indexes:{index}", exc)
                return

    async def migrate_users_add_speech_style(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS speech_style TEXT DEFAULT 'formal';",
                execute=True,
            )
            await self.execute(
                "UPDATE users SET speech_style = 'formal' WHERE speech_style IS NULL OR speech_style = '';",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_speech_style", exc)
            return

    async def migrate_internal_test_accounts(self):
        try:
            from data import config

            rows = await self.execute(
                "SELECT telegram_id, full_name, username FROM users",
                fetch=True,
            )
            for row in rows:
                is_internal = config.is_internal_test_account(
                    full_name=row["full_name"] or "",
                    username=row["username"] or "",
                    telegram_id=row["telegram_id"],
                )
                await self.execute(
                    "UPDATE users SET is_internal_account = $2 WHERE telegram_id = $1",
                    row["telegram_id"], is_internal, execute=True,
                )
        except Exception as exc:
            self._log_migration_failure("migrate_internal_test_accounts", exc)
            return

    async def migrate_account_aware_schema(self):
        statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
            "ALTER TABLE student_parent ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
            "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
            "ALTER TABLE homework ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
            "ALTER TABLE calendar_student_links ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES accounts(id);",
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"migrate_account_aware_schema:{index}", exc)
                return

    async def migrate_owner_role(self):
        try:
            await self.execute(
                """
                UPDATE users
                SET role = 'owner'
                WHERE role = 'teacher_admin'
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_owner_role", exc)
            return

    async def migrate_lessons_add_balance_consumed(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS balance_consumed BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_balance_consumed", exc)
            return

    async def migrate_lessons_add_homework_check_flag(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS homework_check_reminder_sent BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_homework_check_flag", exc)
            return

    async def migrate_lessons_add_source(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';",
                execute=True,
            )
            await self.execute(
                "UPDATE lessons SET source = 'manual' WHERE source IS NULL;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_source", exc)
            return

    async def migrate_calendar_links_indexes(self):
        try:
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS calendar_student_links_student_id_idx
                ON calendar_student_links (student_id)
                WHERE is_active = true;
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS calendar_student_links_alias_unique_idx
                ON calendar_student_links (student_id, LOWER(COALESCE(calendar_alias, '')), LOWER(COALESCE(calendar_event_pattern, '')))
                WHERE is_active = true;
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_calendar_links_indexes", exc)
            return

    async def backfill_default_account_context(self):
        account_id = self.require_account_id()
        try:
            for table_name in [
                "users",
                "student_parent",
                "lessons",
                "homework",
                "payments",
                "calendar_student_links",
            ]:
                await self.execute(
                    f"UPDATE {table_name} SET account_id = $1 WHERE account_id IS NULL",
                    account_id,
                    execute=True,
                )
        except Exception as exc:
            self._log_migration_failure("backfill_default_account_context", exc)
            return

    async def backfill_account_users(self):
        account_id = self.require_account_id()
        try:
            rows = await self.execute(
                """
                SELECT telegram_id, role
                FROM users
                WHERE account_id = $1
                """,
                account_id,
                fetch=True,
            )
            for row in rows:
                role = row["role"]
                if role not in {"owner", "manager", "assistant", "student", "parent"}:
                    role = "owner"
                await self.execute(
                    """
                    INSERT INTO account_users (account_id, telegram_id, role, status)
                    VALUES ($1, $2, $3, 'active')
                    ON CONFLICT (account_id, telegram_id) DO UPDATE
                    SET role = EXCLUDED.role,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    account_id,
                    row["telegram_id"],
                    role,
                    execute=True,
                )
                if role == "owner":
                    await self.execute(
                        """
                        UPDATE accounts
                        SET owner_user_id = COALESCE(owner_user_id, $2),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                        """,
                        account_id,
                        row["telegram_id"],
                        execute=True,
                    )
        except Exception as exc:
            self._log_migration_failure("backfill_account_users", exc)
            return

    async def backfill_global_identities(self):
        try:
            rows = await self.execute(
                """
                SELECT telegram_id, full_name, username
                FROM users
                WHERE telegram_id IS NOT NULL
                ORDER BY telegram_id
                """,
                fetch=True,
            )
            for row in rows:
                await self.execute(
                    """
                    INSERT INTO global_identities (telegram_id, full_name, username, status, updated_at, last_seen_at)
                    VALUES ($1, $2, $3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), global_identities.full_name),
                        username = COALESCE(NULLIF(EXCLUDED.username, ''), global_identities.username),
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    row["telegram_id"],
                    row.get("full_name") or "",
                    row.get("username") or "",
                    execute=True,
                )
            await self.execute(
                """
                UPDATE users u
                SET identity_id = gi.id
                FROM global_identities gi
                WHERE u.telegram_id = gi.telegram_id
                  AND (u.identity_id IS NULL OR u.identity_id <> gi.id)
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("backfill_global_identities", exc)
            return

    async def backfill_account_user_identities(self):
        try:
            await self.execute(
                """
                UPDATE account_users au
                SET identity_id = gi.id
                FROM global_identities gi
                WHERE au.telegram_id = gi.telegram_id
                  AND (au.identity_id IS NULL OR au.identity_id <> gi.id)
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("backfill_account_user_identities", exc)
            return

    async def backfill_domain_user_refs(self):
        statements = [
            """
            UPDATE student_parent sp
            SET student_user_id = u.id
            FROM users u
            WHERE sp.account_id = u.account_id
              AND sp.student_id = u.telegram_id
              AND (sp.student_user_id IS NULL OR sp.student_user_id <> u.id)
            """,
            """
            UPDATE student_parent sp
            SET parent_user_id = u.id
            FROM users u
            WHERE sp.account_id = u.account_id
              AND sp.parent_id = u.telegram_id
              AND (sp.parent_user_id IS NULL OR sp.parent_user_id <> u.id)
            """,
            """
            UPDATE lessons l
            SET student_user_id = u.id
            FROM users u
            WHERE l.account_id = u.account_id
              AND l.student_id = u.telegram_id
              AND (l.student_user_id IS NULL OR l.student_user_id <> u.id)
            """,
            """
            UPDATE homework h
            SET student_user_id = u.id
            FROM users u
            WHERE h.account_id = u.account_id
              AND h.student_id = u.telegram_id
              AND (h.student_user_id IS NULL OR h.student_user_id <> u.id)
            """,
            """
            UPDATE payments p
            SET student_user_id = u.id
            FROM users u
            WHERE p.account_id = u.account_id
              AND p.student_id = u.telegram_id
              AND (p.student_user_id IS NULL OR p.student_user_id <> u.id)
            """,
            """
            UPDATE payments p
            SET payer_user_id = u.id
            FROM users u
            WHERE p.account_id = u.account_id
              AND p.payer_id = u.telegram_id
              AND (p.payer_user_id IS NULL OR p.payer_user_id <> u.id)
            """,
            """
            UPDATE calendar_student_links csl
            SET student_user_id = u.id
            FROM users u
            WHERE csl.account_id = u.account_id
              AND csl.student_id = u.telegram_id
              AND (csl.student_user_id IS NULL OR csl.student_user_id <> u.id)
            """,
            """
            UPDATE group_members gm
            SET student_user_id = u.id
            FROM groups g
            JOIN users u
              ON u.account_id = g.account_id
            WHERE gm.group_id = g.id
              AND gm.student_id = u.telegram_id
              AND (gm.student_user_id IS NULL OR gm.student_user_id <> u.id)
            """,
        ]
        for index, statement in enumerate(statements, start=1):
            try:
                await self.execute(statement, execute=True)
            except Exception as exc:
                self._log_migration_failure(f"backfill_domain_user_refs:{index}", exc)
                return

    async def verify_required_schema(self):
        required_columns = {
            "global_identities": {
                "telegram_id",
                "status",
            },
            "accounts": {
                "code",
                "name",
                "slug",
                "status",
                "is_default",
            },
            "users": {
                "account_id",
                "identity_id",
                "language",
                "level",
                "age",
                "review_sent",
                "lesson_reminders",
                "is_internal_account",
                "lesson_format",
                "speech_style",
            },
            "student_parent": {"account_id", "student_user_id", "parent_user_id"},
            "lessons": {
                "account_id",
                "student_user_id",
                "lesson_date",
                "reminder_sent",
                "balance_consumed",
                "homework_check_reminder_sent",
                "source",
            },
            "homework": {"account_id", "student_user_id", "reminder_sent"},
            "payments": {"account_id", "student_user_id", "payer_user_id"},
            "calendar_student_links": {"account_id", "student_user_id"},
            "plans": {"code", "display_name"},
            "subscriptions": {"account_id", "plan_code", "status", "trial_ends_at", "paid_until"},
            "account_users": {"account_id", "identity_id", "telegram_id", "role"},
            "account_feature_overrides": {"account_id", "capability", "is_enabled"},
            "account_invites": {"account_id", "token", "role", "status"},
            "groups": {"account_id", "name", "is_active"},
            "group_members": {"group_id", "student_id", "student_user_id"},
        }

        rows = await self.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_name = ANY($1::text[])
            """,
            list(required_columns.keys()),
            fetch=True,
        )
        present = {}
        for row in rows:
            present.setdefault(row["table_name"], set()).add(row["column_name"])

        missing = []
        for table_name, columns in required_columns.items():
            absent = sorted(columns - present.get(table_name, set()))
            if absent:
                missing.append(f"{table_name}: {', '.join(absent)}")

        if missing:
            raise RuntimeError(
                "Database schema is incomplete. Missing columns: " + " | ".join(missing)
            )

    async def create_all_tables(self):
        await self.create_table_global_identities()
        await self.create_table_accounts()
        await self.create_table_users()
        await self.create_table_student_parent()
        await self.create_table_lessons()
        await self.create_table_payments()
        await self.create_table_homework()
        await self.create_table_calendar_student_links()
        await self.create_table_plans()
        await self.create_table_subscriptions()
        await self.create_table_account_users()
        await self.create_table_account_feature_overrides()
        await self.create_table_account_invites()
        await self.create_table_groups()
        await self.create_table_group_members()
        await self.migrate_lessons_google_event_id()
        await self.migrate_lessons_add_date()
        await self.migrate_lessons_google_event_id_unique()
        await self.migrate_lessons_add_reminder_sent()
        await self.migrate_users_add_language_level()
        await self.migrate_users_add_lesson_format()
        await self.migrate_users_add_speech_style()
        await self.migrate_identity_split_columns()
        await self.migrate_identity_split_indexes()
        await self.migrate_users_account_scoped_unique_index()
        await self.migrate_domain_user_ref_columns()
        await self.migrate_domain_user_ref_indexes()
        await self.migrate_drop_legacy_user_telegram_foreign_keys()
        await self.migrate_internal_test_accounts()
        await self.migrate_account_aware_schema()
        await self.migrate_owner_role()
        await self.migrate_lessons_add_balance_consumed()
        await self.migrate_lessons_add_homework_check_flag()
        await self.migrate_lessons_add_source()
        await self.migrate_calendar_links_indexes()
        await self.seed_default_plans()
        await self.ensure_default_account()
        await self.backfill_default_account_context()
        await self.backfill_global_identities()
        await self.ensure_default_subscription()
        await self.backfill_account_users()
        await self.backfill_account_user_identities()
        await self.backfill_domain_user_refs()
        await self.verify_required_schema()
