from data.config import normalize_person_name
from utils.text_utils import extract_student_name


class DatabaseUserMixin:
    async def get_user(self, telegram_id: int):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                u.*,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.account_id = $2
                      AND l.lesson_date IS NOT NULL
                ) AS first_lesson_date
            FROM users u
            WHERE u.telegram_id = $1
              AND u.account_id = $2
            """,
            telegram_id, account_id, fetchrow=True,
        )

    async def get_all_students(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT *
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

    async def find_active_student_by_name(self, full_name: str):
        normalized_target = normalize_person_name(full_name)
        if not normalized_target:
            return None
        students = await self.get_all_students()
        for student in students:
            if normalize_person_name(student.get("full_name") or "") == normalized_target:
                return student
        return None

    async def upsert_parent_student_link(self, parent_id: int, student_info: str, student_id: int | None = None):
        account_id = self.require_account_id()
        normalized_target = normalize_person_name(extract_student_name(student_info))
        links = await self.execute(
            """
            SELECT id, student_info, student_id
            FROM student_parent
            WHERE parent_id = $1
              AND account_id = $2
              AND is_active = true
            ORDER BY id
            """,
            parent_id,
            account_id,
            fetch=True,
        )
        for link in links:
            normalized_existing = normalize_person_name(extract_student_name(link.get("student_info") or ""))
            if normalized_existing == normalized_target:
                await self.execute(
                    """
                    UPDATE student_parent
                    SET student_info = $2,
                        student_id = $3,
                        is_active = true
                    WHERE id = $1
                    """,
                    link["id"],
                    student_info,
                    student_id,
                    execute=True,
                )
                return link["id"]

        return await self.execute(
            """
            INSERT INTO student_parent (account_id, parent_id, student_id, student_info)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            account_id,
            parent_id,
            student_id,
            student_info,
            fetchval=True,
        )

    async def sync_parent_links_for_student(self, student_id: int, full_name: str):
        account_id = self.require_account_id()
        normalized_student_name = normalize_person_name(full_name)
        if not normalized_student_name:
            return 0
        links = await self.execute(
            """
            SELECT id, student_info, student_id
            FROM student_parent
            WHERE account_id = $1
              AND is_active = true
            """,
            account_id,
            fetch=True,
        )
        updated = 0
        for link in links:
            normalized_link_name = normalize_person_name(extract_student_name(link.get("student_info") or ""))
            if normalized_link_name != normalized_student_name:
                continue
            if link.get("student_id") == student_id:
                continue
            await self.execute(
                "UPDATE student_parent SET student_id = $2 WHERE id = $1",
                link["id"],
                student_id,
                execute=True,
            )
            updated += 1
        return updated

    async def sync_all_parent_links(self):
        students = await self.get_all_students()
        updated = 0
        for student in students:
            updated += await self.sync_parent_links_for_student(
                student["telegram_id"],
                student["full_name"],
            )
        return updated

    async def get_parent_children(self, parent_id: int) -> list[str]:
        account_id = self.require_account_id()
        links = await self.execute(
            """
            SELECT sp.student_info, sp.student_id, u.full_name
            FROM student_parent sp
            LEFT JOIN users u
              ON u.telegram_id = sp.student_id
             AND u.account_id = $2
            WHERE sp.parent_id = $1
              AND sp.account_id = $2
              AND sp.is_active = true
            ORDER BY sp.id
            """,
            parent_id,
            account_id,
            fetch=True,
        )
        items = []
        seen = set()
        for link in links:
            label = link.get("full_name") or link.get("student_info") or ""
            dedupe_key = normalize_person_name(extract_student_name(label))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            if label:
                items.append(label)
        return items

    async def get_students_overview(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                u.language,
                u.level,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = u.telegram_id
                      AND p.account_id = $1
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.account_id = $1
                      AND l.lesson_date IS NOT NULL
                ) AS first_lesson_date,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.account_id = $1
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.speech_style, 'formal') AS speech_style
            FROM users u
            WHERE u.account_id = $1
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            account_id,
            fetch=True,
        )

    async def get_students_with_calendar_alias_counts(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(COUNT(csl.id), 0)::int AS alias_count
            FROM users u
            LEFT JOIN calendar_student_links csl
              ON csl.student_id = u.telegram_id
             AND csl.account_id = $1
             AND csl.is_active = true
            WHERE u.account_id = $1
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            GROUP BY u.telegram_id, u.full_name
            ORDER BY u.full_name
            """,
            account_id,
            fetch=True,
        )

    async def deactivate_student(self, telegram_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE users SET is_active = false WHERE telegram_id = $1 AND account_id = $2",
            telegram_id,
            account_id,
            execute=True,
        )

    async def delete_student(self, telegram_id: int):
        await self.delete_user_fully(telegram_id)

    async def get_user_deletion_snapshot(self, telegram_id: int) -> dict:
        account_id = self.require_account_id()
        user = await self.get_user(telegram_id)
        if not user:
            return {}

        return {
            "role": user["role"],
            "homework": await self.execute(
                "SELECT COUNT(*) FROM homework WHERE student_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "lessons": await self.execute(
                "SELECT COUNT(*) FROM lessons WHERE student_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "payments_as_student": await self.execute(
                "SELECT COUNT(*) FROM payments WHERE student_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "payments_as_payer": await self.execute(
                "SELECT COUNT(*) FROM payments WHERE payer_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "calendar_links": await self.execute(
                "SELECT COUNT(*) FROM calendar_student_links WHERE student_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "parent_links_as_student": await self.execute(
                "SELECT COUNT(*) FROM student_parent WHERE student_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
            "parent_links_as_parent": await self.execute(
                "SELECT COUNT(*) FROM student_parent WHERE parent_id = $1 AND account_id = $2",
                telegram_id, account_id, fetchval=True,
            ) or 0,
        }

    async def delete_user_fully(self, telegram_id: int):
        account_id = self.require_account_id()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM calendar_student_links WHERE student_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM homework WHERE student_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM lessons WHERE student_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM payments WHERE account_id = $2 AND (student_id = $1 OR payer_id = $1)",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM student_parent WHERE parent_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM student_parent WHERE student_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    """
                    DELETE FROM account_users
                    WHERE account_id = $2
                      AND telegram_id = $1
                    """,
                    telegram_id,
                    account_id,
                )
                await conn.execute(
                    "DELETE FROM users WHERE telegram_id = $1 AND account_id = $2",
                    telegram_id,
                    account_id,
                )

    async def get_students_for_review(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                MIN(l.lesson_date) AS first_lesson
            FROM users u
            JOIN lessons l
              ON l.student_id = u.telegram_id
             AND l.account_id = $1
            WHERE u.account_id = $1
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
              AND u.review_sent = false
              AND l.lesson_date IS NOT NULL
            GROUP BY u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal')
            HAVING MIN(l.lesson_date) <= NOW() - INTERVAL '21 days'
            """,
            account_id,
            fetch=True,
        )

    async def mark_review_sent(self, telegram_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE users SET review_sent = true WHERE telegram_id = $1 AND account_id = $2",
            telegram_id,
            account_id,
            execute=True,
        )

    async def get_students_with_balances(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                COALESCE(SUM(p.lessons_remaining), 0)::int AS lesson_balance
            FROM users u
            LEFT JOIN payments p
              ON p.student_id = u.telegram_id
             AND p.account_id = $1
             AND p.status = 'confirmed'
            WHERE u.account_id = $1
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            GROUP BY u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal')
            ORDER BY u.full_name
            """,
            account_id,
            fetch=True,
        )

    async def set_speech_style(self, telegram_id: int, value: str):
        account_id = self.require_account_id()
        await self.execute(
            "UPDATE users SET speech_style = $1 WHERE telegram_id = $2 AND account_id = $3",
            value,
            telegram_id,
            account_id,
            execute=True,
        )

    async def get_admin_dashboard_snapshot(self):
        account_id = self.require_account_id()
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
                    FROM lessons l
                    JOIN users u
                      ON u.telegram_id = l.student_id
                     AND u.account_id = $1
                    WHERE l.status = 'active'
                      AND l.account_id = $1
                      AND l.lesson_date IS NOT NULL
                      AND l.lesson_date::date = CURRENT_DATE
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS lessons_today,
                (
                    SELECT COUNT(*)::int
                    FROM (
                        SELECT u.telegram_id
                        FROM users u
                        LEFT JOIN payments p
                          ON p.student_id = u.telegram_id
                         AND p.account_id = $1
                         AND p.status = 'confirmed'
                        WHERE u.account_id = $1
                          AND u.role = 'student'
                          AND u.is_active = true
                          AND COALESCE(u.is_internal_account, false) = false
                        GROUP BY u.telegram_id
                        HAVING COALESCE(SUM(p.lessons_remaining), 0) = 0
                    ) unpaid
                ) AS unpaid_students,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    JOIN users u
                      ON u.telegram_id = l.student_id
                     AND u.account_id = $1
                    WHERE l.status = 'freeze_pending'
                      AND l.account_id = $1
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS pending_freezes,
                (
                    SELECT COUNT(*)::int
                    FROM homework h
                    JOIN users u
                      ON u.telegram_id = h.student_id
                     AND u.account_id = $1
                    WHERE h.status = 'active'
                      AND h.account_id = $1
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS active_homework,
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
                          WHERE l.student_id = u.telegram_id
                            AND l.account_id = $1
                            AND l.status = 'active'
                            AND l.lesson_date IS NOT NULL
                            AND l.lesson_date >= NOW()
                      )
                ) AS students_without_upcoming_lessons
            """,
            account_id,
            fetchrow=True,
        )

    async def get_parent_weekly_digest_rows(self, period_start, period_end):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                parent.telegram_id AS parent_id,
                parent.full_name AS parent_name,
                student.telegram_id AS student_id,
                student.full_name AS student_name,
                EXISTS (
                    SELECT 1
                    FROM lessons l
                    WHERE l.student_id = student.telegram_id
                      AND l.account_id = $3
                      AND l.lesson_date >= $1
                      AND l.lesson_date < $2
                      AND l.status IN ('active', 'completed', 'freeze_pending', 'frozen')
                ) AS had_lesson,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = student.telegram_id
                      AND h.account_id = $3
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = student.telegram_id
                      AND p.account_id = $3
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance
            FROM student_parent sp
            JOIN users parent
              ON parent.telegram_id = sp.parent_id
             AND parent.account_id = $3
             AND parent.role = 'parent'
             AND parent.is_active = true
            JOIN users student
              ON student.telegram_id = sp.student_id
             AND student.account_id = $3
             AND student.role = 'student'
             AND student.is_active = true
            WHERE sp.account_id = $3
              AND sp.is_active = true
            ORDER BY parent.full_name, student.full_name
            """,
            period_start,
            period_end,
            account_id,
            fetch=True,
        )
