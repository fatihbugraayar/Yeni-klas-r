from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from telegram_bot.database.models import Base


class Database:
    def __init__(self, url: str):
        parsed = make_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        if parsed.drivername.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def configure_sqlite(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

    async def initialize(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(self._migrate_ai_studio)

    @staticmethod
    def _migrate_ai_studio(connection):
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "free_ai_studio_credits" not in columns:
            # Add only the new allowance; preserve existing quotas, jobs and receipts.
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN free_ai_studio_credits "
                    "INTEGER NOT NULL DEFAULT 1 CHECK (free_ai_studio_credits >= 0)"
                )
            )

    async def close(self):
        await self.engine.dispose()
