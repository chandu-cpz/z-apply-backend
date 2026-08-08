from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    sessions: async_sessionmaker[AsyncSession],
    *,
    begin: bool = False,
) -> AsyncIterator[AsyncSession]:
    """Yield a session and guarantee it returns to the pool even when the
    enclosing task is cancelled (SSE client disconnects, aborted requests).

    uvicorn cancels request handlers through an anyio cancel scope; once a
    task is cancelled inside such a scope, every subsequent await raises
    ``CancelledError``, which would interrupt an unguarded ``session.close()``
    and leak the asyncpg connection. The leak is later GC-terminated with a
    loud pool warning and can stall ``engine.dispose()`` at shutdown (the
    observed backend hang). Running the close inside ``shield`` lets it
    complete in its own task even while the caller is being cancelled.
    """
    session = sessions()
    try:
        if begin:
            async with session.begin():
                yield session
        else:
            yield session
    finally:
        await asyncio.shield(session.close())
