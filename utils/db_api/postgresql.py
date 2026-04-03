from contextvars import ContextVar
from typing import Union

import asyncpg
from asyncpg import Connection
from asyncpg.pool import Pool

from data import config
from utils.db_api.business import DatabaseBusinessMixin
from utils.db_api.calendar_links import DatabaseCalendarLinksMixin
from utils.db_api.homework import DatabaseHomeworkMixin
from utils.db_api.lessons import DatabaseLessonMixin
from utils.db_api.payments import DatabasePaymentMixin
from utils.db_api.schema import DatabaseSchemaMixin
from utils.db_api.users import DatabaseUserMixin


class Database(
    DatabaseBusinessMixin,
    DatabaseSchemaMixin,
    DatabaseUserMixin,
    DatabaseHomeworkMixin,
    DatabaseCalendarLinksMixin,
    DatabaseLessonMixin,
    DatabasePaymentMixin,
):
    def __init__(self):
        self.pool: Union[Pool, None] = None
        self._account_id_var: ContextVar[int | None] = ContextVar("database_account_id", default=None)
        self._default_account_id: int | None = None

    @property
    def account_id(self) -> int | None:
        return self._account_id_var.get() if self._account_id_var.get() is not None else self._default_account_id

    @account_id.setter
    def account_id(self, value: int | None):
        self._default_account_id = value
        self._account_id_var.set(value)

    def push_account_context(self, account_id: int | None):
        return self._account_id_var.set(account_id)

    def reset_account_context(self, token):
        self._account_id_var.reset(token)

    async def create_pool(self):
        self.pool = await asyncpg.create_pool(
            user=config.PGUSER,
            password=config.PGPASSWORD,
            host=config.PGHOST,
            port=int(config.PGPORT),
            database=config.DATABASE,
            server_settings={"TimeZone": "Europe/Moscow"},
        )

    async def execute(
        self,
        command,
        *args,
        fetch: bool = False,
        fetchval: bool = False,
        fetchrow: bool = False,
        execute: bool = False,
    ):
        async with self.pool.acquire() as connection:
            connection: Connection
            async with connection.transaction():
                if fetch:
                    result = await connection.fetch(command, *args)
                elif fetchval:
                    result = await connection.fetchval(command, *args)
                elif fetchrow:
                    result = await connection.fetchrow(command, *args)
                elif execute:
                    result = await connection.execute(command, *args)
                else:
                    result = None
            return result
