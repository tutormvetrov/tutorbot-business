class DatabasePaymentMixin:
    async def get_student_payments(self, payer_id: int, limit: int = 5):
        account_id = self.require_account_id()
        return await self.execute(
            """
            SELECT * FROM payments
            WHERE payer_id = $1
              AND account_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            payer_id, account_id, limit, fetch=True,
        )

    async def get_payment_by_id(self, payment_id: int):
        account_id = self.require_account_id()
        return await self.execute(
            "SELECT * FROM payments WHERE id = $1 AND account_id = $2",
            payment_id,
            account_id,
            fetchrow=True,
        )

    async def delete_payment(self, payment_id: int):
        account_id = self.require_account_id()
        await self.execute(
            "DELETE FROM payments WHERE id = $1 AND account_id = $2",
            payment_id,
            account_id,
            execute=True,
        )

    async def add_payment(self, student_id: int, amount: float, lessons_count: int):
        account_id = self.require_account_id()
        return await self.execute(
            """
            INSERT INTO payments
                (account_id, payer_id, student_id, amount, lessons_count, lessons_remaining, status, payment_date)
            VALUES ($1, $2, $2, $3, $4, $4, 'confirmed', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            account_id, student_id, amount, lessons_count, fetchval=True,
        )
