from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def session_scope(app) -> AsyncIterator[AsyncSession]:
    """Open one database session for the duration of the `async with` block.

    The single place a session is built, so HTTP requests and WebSocket
    handshakes never diverge into two session configurations. Callers that
    are not FastAPI request dependencies (a WebSocket handshake, a periodic
    re-verification tick) use this directly, precisely so their session is
    scoped to the work rather than to the connection.

    Args:
        app: The FastAPI app, read for its DI container.

    Yields:
        An open session, closed when the block exits.
    """
    db = await app.container.database()
    async with db.session_factory() as session:
        yield session


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session scoped to the current HTTP request.

    Args:
        request: The incoming request, read for its app and DI container.

    Yields:
        An open session, closed when the request ends.
    """
    async with session_scope(request.app) as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
