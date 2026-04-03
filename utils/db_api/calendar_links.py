class DatabaseCalendarLinksMixin:
    async def get_calendar_student_links(self):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT
                csl.*,
                u.full_name
            FROM calendar_student_links csl
            JOIN users u ON (csl.student_user_id = u.id OR (csl.student_user_id IS NULL AND u.telegram_id = csl.student_id))
                        AND u.account_id = $1
            WHERE csl.is_active = true
              AND csl.account_id = $1
            ORDER BY u.full_name, csl.id
            """,
            account_id,
            fetch=True,
        )

    async def get_calendar_student_links_for_student(self, student_id: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        return await self.execute(
            """
            SELECT *
            FROM calendar_student_links
            WHERE account_id = $2
              AND (student_id = $1 OR student_user_id = $3)
              AND is_active = true
            ORDER BY id
            """,
            student_id, account_id, student_user_id, fetch=True,
        )

    async def replace_calendar_student_links(self, student_id: int, items: list[dict]):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM calendar_student_links
                    WHERE account_id = $2
                      AND (student_id = $1 OR student_user_id = $3)
                    """,
                    student_id,
                    account_id,
                    student_user_id,
                )
                for item in items:
                    alias = item.get("calendar_alias")
                    pattern = item.get("calendar_event_pattern")
                    await conn.execute(
                        """
                        INSERT INTO calendar_student_links (account_id, student_user_id, student_id, calendar_alias, calendar_event_pattern)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        account_id,
                        student_user_id,
                        student_id,
                        alias,
                        pattern,
                    )

    async def clear_calendar_student_links(self, student_id: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        await self.execute(
            """
            DELETE FROM calendar_student_links
            WHERE account_id = $2
              AND (student_id = $1 OR student_user_id = $3)
            """,
            student_id,
            account_id,
            student_user_id,
            execute=True,
        )
