from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"timeout": 30} if settings.is_sqlite else {}
engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args)

if settings.is_sqlite:
    # SQLite has no row locks. BEGIN IMMEDIATE takes the write lock up front, which
    # serialises concurrent check-ins the same way SELECT ... FOR UPDATE does on Postgres.
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _sqlite_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with SessionLocal() as session:
        yield session
