from utils.domain_errors import PaymentIntegrityError


class DatabasePaymentMixin:
    async def get_student_payments(self, payer_id: int, limit: int = 5):
        account_id = self.require_account_id()
        payer_user_id = await self.get_user_row_id(payer_id)
        return await self.execute(
            """
            SELECT * FROM payments
            WHERE account_id = $2
              AND (payer_id = $1 OR payer_user_id = $3)
            ORDER BY created_at DESC
            LIMIT $4
            """,
            payer_id, account_id, payer_user_id, limit, fetch=True,
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
        payment = await self.get_payment_by_id(payment_id)
        if not payment:
            return False
        payment = dict(payment)
        lessons_count = int(payment.get("lessons_count") or 0)
        lessons_remaining = int(payment.get("lessons_remaining") or 0)
        if lessons_remaining != lessons_count:
            raise PaymentIntegrityError(
                "Нельзя удалять оплату, по которой уже были списаны уроки."
            )
        await self.execute(
            "DELETE FROM payments WHERE id = $1 AND account_id = $2",
            payment_id,
            account_id,
            execute=True,
        )
        return True

    async def add_payment(self, student_id: int, amount: float, lessons_count: int):
        account_id = self.require_account_id()
        student_user_id = await self.get_user_row_id(student_id)
        return await self.execute(
            """
            INSERT INTO payments
                (
                    account_id,
                    payer_user_id,
                    student_user_id,
                    payer_id,
                    student_id,
                    amount,
                    lessons_count,
                    lessons_remaining,
                    status,
                    payment_date
                )
            VALUES ($1, $2, $2, $3, $3, $4, $5, $5, 'confirmed', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            account_id, student_user_id, student_id, amount, lessons_count, fetchval=True,
        )
