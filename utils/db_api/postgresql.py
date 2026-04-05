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

    def _build_search_path(self) -> str:
        schema = (config.PGSCHEMA or "public").strip()
        if schema == "public":
            return "public"
        return f'{self._quote_identifier(schema)}, public'

    async def _ensure_operational_schema(self):
        schema = (config.PGSCHEMA or "public").strip()
        if not schema or schema == "public":
            return
        connection = await asyncpg.connect(
            user=config.PGUSER,
            password=config.PGPASSWORD,
            host=config.PGHOST,
            port=int(config.PGPORT),
            database=config.DATABASE,
        )
        try:
            await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)};")
        finally:
            await connection.close()

    async def create_pool(self):
        await self._ensure_operational_schema()

        async def _init_connection(connection: Connection):
            await connection.execute(f"SET search_path TO {self._build_search_path()};")
            await connection.execute("SET TIME ZONE 'UTC';")

        self.pool = await asyncpg.create_pool(
            user=config.PGUSER,
            password=config.PGPASSWORD,
            host=config.PGHOST,
            port=int(config.PGPORT),
            database=config.DATABASE,
            init=_init_connection,
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
