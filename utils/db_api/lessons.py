from typing import Optional


class DatabaseLessonMixin:
    async def get_lessons_for_reminder(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                l.*,
                u.telegram_id,
                u.full_name,
                u.lesson_reminders,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.speech_style, 'formal') AS speech_style
            FROM lessons l
            JOIN users u ON (l.student_user_id = u.id OR (l.student_user_id IS NULL AND u.telegram_id = l.student_id))
                       AND u.account_id = $1
            WHERE l.status = 'active'
              AND l.account_id = $1
              AND l.reminder_sent = false
              AND (u.lesson_reminders = 'enabled'
                   OR u.lesson_reminders LIKE 'paused_until:%')
              AND (
                  (
                      COALESCE(u.lesson_format, 'online') != 'offline'
                      AND l.lesson_date >= NOW() + INTERVAL '5 minutes'
                      AND l.lesson_date <= NOW() + INTERVAL '15 minutes'
                  )
                  OR
                  (
                      COALESCE(u.lesson_format, 'online') = 'offline'
                      AND l.lesson_date >= NOW() + INTERVAL '55 minutes'
                      AND l.lesson_date <= NOW() + INTERVAL '65 minutes'
                  )
              )
            """,
            account_id,
            fetch=True,
        )

    async def mark_lesson_reminder_sent(self, lesson_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE lessons SET reminder_sent=true WHERE id=$1 AND account_id = $2",
            lesson_id,
            account_id,
            execute=True,
        )

    async def get_lessons_missing_homework(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            WITH next_lessons AS (
                SELECT DISTINCT ON (COALESCE(l.student_user_id, u.id))
                    l.id,
                    l.student_id,
                    COALESCE(l.student_user_id, u.id) AS student_user_id,
                    l.lesson_date,
                    u.full_name
                FROM lessons l
                JOIN users u ON (l.student_user_id = u.id OR (l.student_user_id IS NULL AND u.telegram_id = l.student_id))
                            AND u.account_id = $1
                WHERE l.status = 'active'
                  AND l.account_id = $1
                  AND l.lesson_date IS NOT NULL
                  AND l.homework_check_reminder_sent = false
                  AND l.lesson_date > NOW()
                  AND l.lesson_date <= NOW() + INTERVAL '24 hours'
                  AND u.role = 'student'
                  AND u.is_active = true
                  AND COALESCE(u.is_internal_account, false) = false
                ORDER BY COALESCE(l.student_user_id, u.id), l.lesson_date ASC
            ),
            previous_lessons AS (
                SELECT
                    n.id AS next_lesson_id,
                    MAX(l.lesson_date) AS previous_lesson_date
                FROM next_lessons n
                JOIN lessons l ON (
                    l.student_user_id = n.student_user_id
                    OR (
                        l.student_user_id IS NULL
                        AND l.student_id = n.student_id
                    )
                )
                WHERE l.lesson_date IS NOT NULL
                  AND l.account_id = $1
                  AND l.lesson_date < n.lesson_date
                  AND l.status IN ('active', 'completed')
                GROUP BY n.id
            )
            SELECT
                n.id,
                n.student_id,
                n.student_user_id,
                n.lesson_date,
                n.full_name,
                p.previous_lesson_date
            FROM next_lessons n
            JOIN previous_lessons p ON p.next_lesson_id = n.id
            WHERE NOT EXISTS (
                SELECT 1
                FROM homework h
                WHERE (
                        h.student_user_id = n.student_user_id
                        OR (
                            h.student_user_id IS NULL
                            AND h.student_id = n.student_id
                        )
                      )
                  AND h.account_id = $1
                  AND h.created_at >= p.previous_lesson_date
                  AND h.created_at <= n.lesson_date
            )
            ORDER BY n.lesson_date ASC
            """,
            account_id,
            fetch=True,
        )

    async def mark_homework_check_reminder_sent(self, lesson_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE lessons SET homework_check_reminder_sent = true WHERE id = $1 AND account_id = $2",
            lesson_id,
            account_id,
            execute=True,
        )

    async def set_lesson_reminders(self, telegram_id: int, value: str):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE users SET lesson_reminders=$1 WHERE telegram_id=$2 AND account_id = $3",
            value, telegram_id, account_id, execute=True,
        )

    async def set_lesson_format(self, telegram_id: int, value: str):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE users SET lesson_format=$1 WHERE telegram_id=$2 AND account_id = $3",
            value, telegram_id, account_id, execute=True,
        )

    async def get_active_lessons(self, student_id: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        return await self.execute(
            """
            SELECT * FROM lessons
            WHERE account_id = $2
              AND (student_id = $1 OR student_user_id = $3)
              AND status = 'active'
            ORDER BY lesson_date ASC NULLS LAST, created_at DESC
            """,
            student_id, account_id, student_user_id, fetch=True,
        )

    async def get_pending_freeze_lessons(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT l.*, u.full_name, u.telegram_id AS user_telegram_id
            FROM lessons l
            JOIN users u ON (l.student_user_id = u.id OR (l.student_user_id IS NULL AND u.telegram_id = l.student_id))
                        AND u.account_id = $1
            WHERE l.status = 'freeze_pending'
              AND l.account_id = $1
            ORDER BY l.created_at ASC
            """,
            account_id,
            fetch=True,
        )

    async def add_lesson(self, student_id: int, lesson_date, google_event_id: Optional[str] = None):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        await self.execute(
            """
            INSERT INTO lessons (account_id, student_user_id, student_id, lesson_date, google_event_id, status, source)
            VALUES ($1, $2, $3, $4, $5, 'active', 'manual')
            """,
            account_id, student_user_id, student_id, lesson_date, google_event_id, execute=True,
        )

    async def upsert_lesson_from_calendar(self, student_id: int, google_event_id: str, lesson_date):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        existing = await self.execute(
            "SELECT id FROM lessons WHERE google_event_id = $1 AND account_id = $2",
            google_event_id,
            account_id,
            fetchrow=True,
        )
        if existing:
            await self.execute(
                """
                UPDATE lessons
                SET lesson_date = $2,
                    student_id = $3,
                    student_user_id = $4,
                    status = 'active',
                    source = 'calendar'
                WHERE google_event_id = $1
                  AND account_id = $5
                """,
                google_event_id, lesson_date, student_id, student_user_id, account_id, execute=True,
            )
            return "updated"

        await self.execute(
            """
            INSERT INTO lessons (account_id, student_user_id, student_id, google_event_id, lesson_date, status, source)
            VALUES ($1, $2, $3, $4, $5, 'active', 'calendar')
            """,
            account_id, student_user_id, student_id, google_event_id, lesson_date, execute=True,
        )
        return "inserted"

    async def approve_freeze(self, lesson_id: int):
        account_id = self.require_account_id()
        await self.execute(
            """
            UPDATE lessons
            SET status = 'frozen', freeze_start_date = CURRENT_TIMESTAMP
            WHERE id = $1
              AND account_id = $2
            """,
            lesson_id, account_id, execute=True,
        )

    async def reject_freeze(self, lesson_id: int):
        account_id = self.require_account_id()
        await self.execute(
            """
            UPDATE lessons
            SET status = 'active',
                freeze_reason = NULL,
                freeze_start_date = NULL
            WHERE id = $1
              AND account_id = $2
            """,
            lesson_id, account_id, execute=True,
        )

    async def get_student_lesson_balance(self, student_id: int) -> int:
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        result = await self.execute(
            """
            SELECT COALESCE(SUM(lessons_remaining), 0)
            FROM payments
            WHERE account_id = $2
              AND (student_id = $1 OR student_user_id = $3)
              AND status = 'confirmed'
            """,
            student_id, account_id, student_user_id, fetchval=True,
        )
        return int(result) if result else 0

    async def get_past_unprocessed_lessons(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT l.id, l.student_id
            FROM lessons l
            WHERE l.account_id = $1
              AND l.status = 'active'
              AND l.balance_consumed = false
              AND l.lesson_date IS NOT NULL
              AND l.lesson_date < NOW()
            """,
            account_id,
            fetch=True,
        )

    async def complete_lesson(self, lesson_id: int, student_id: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE lessons
                    SET status = 'completed', balance_consumed = true
                    WHERE id = $1
                      AND account_id = $2
                    """,
                    lesson_id,
                    account_id,
                )
                payment = await conn.fetchrow(
                    """
                    SELECT id FROM payments
                    WHERE account_id = $2
                      AND (student_id = $1 OR student_user_id = $3)
                      AND status = 'confirmed'
                      AND lessons_remaining > 0
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    student_id,
                    account_id,
                    student_user_id,
                )
                if payment:
                    await conn.execute(
                        "UPDATE payments SET lessons_remaining = lessons_remaining - 1 WHERE id = $1",
                        payment['id'],
                    )

    async def delete_lesson(self, lesson_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "DELETE FROM lessons WHERE id = $1 AND account_id = $2",
            lesson_id,
            account_id,
            execute=True,
        )

    async def get_non_completed_lessons(self, student_id: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        return await self.execute(
            """
            SELECT * FROM lessons
            WHERE account_id = $2
              AND (student_id = $1 OR student_user_id = $3)
              AND status != 'completed'
            ORDER BY lesson_date ASC NULLS LAST
            """,
            student_id, account_id, student_user_id, fetch=True,
        )

    async def get_lessons_in_window(self, start_dt, end_dt):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT id, student_id, lesson_date, status
            FROM lessons
            WHERE account_id = $1
              AND lesson_date IS NOT NULL
              AND lesson_date >= $2
              AND lesson_date < $3
              AND status IN ('active', 'completed', 'freeze_pending')
            ORDER BY lesson_date ASC
            """,
            account_id,
            start_dt,
            end_dt,
            fetch=True,
        )

    async def get_google_event_ids_in_window(self, days_ahead: int = 60) -> list:
        from datetime import datetime, timedelta

        account_id = self.require_account_id()
        now = datetime.now()
        end = now + timedelta(days=days_ahead)
        rows = await self.execute(
            """
            SELECT google_event_id FROM lessons
            WHERE account_id = $1
              AND status != 'completed'
              AND source = 'calendar'
              AND google_event_id IS NOT NULL
              AND lesson_date BETWEEN $2 AND $3
            """,
            account_id, now, end, fetch=True,
        )
        return [r['google_event_id'] for r in rows]

    async def delete_lessons_by_event_ids(self, event_ids: list):
        account_id = self.require_account_id()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM lessons
                WHERE account_id = $1
                  AND source = 'calendar'
                  AND google_event_id = ANY($2::text[])
                """,
                account_id,
                event_ids,
            )
