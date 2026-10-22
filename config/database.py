"""
Setup SQLAlchemy 2.0 async engine / session factory con fallback nativo SQLite.

Supporta:
  1. PostgreSQL via SQLAlchemy 2.0 + asyncpg (quando installato e configurato)
  2. SQLite locale compatibile con FollowTheMoney (dati/aethelburg.sqlite)
"""
from __future__ import annotations

import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from config.settings import get_settings

try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    HAS_SQLALCHEMY = True
except ImportError:
    AsyncSession = Any  # type: ignore[misc,assignment]
    async_sessionmaker = None  # type: ignore[assignment]
    create_async_engine = None  # type: ignore[assignment]
    HAS_SQLALCHEMY = False

_engine: Any = None
_session_factory: Any = None


class LocalSQLiteAsyncSession:
    """Sessione asincrona leggera su sqlite3 quando SQLAlchemy non è installato o DB_BACKEND=sqlite."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")

    async def execute(self, statement: Any, params: dict[str, Any] | tuple[Any, ...] | None = None) -> sqlite3.Cursor:
        sql = str(statement)
        if params is None:
            return self.conn.execute(sql)
        return self.conn.execute(sql, params)

    async def commit(self) -> None:
        self.conn.commit()

    async def rollback(self) -> None:
        self.conn.rollback()

    async def close(self) -> None:
        self.conn.close()


def get_sqlite_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Restituisce una connessione sqlite3 configurata con WAL e foreign_keys=ON."""
    settings = get_settings()
    target = Path(db_path or settings.db.sqlite_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        settings = get_settings()
        if HAS_SQLALCHEMY and settings.db.backend == "postgresql":
            _engine = create_async_engine(
                settings.db.async_url,
                echo=settings.app.debug,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        else:
            _engine = settings.db.sqlite_path
    return _engine


def _get_session_factory() -> Any:
    global _session_factory
    if _session_factory is None:
        settings = get_settings()
        if HAS_SQLALCHEMY and settings.db.backend == "postgresql":
            _session_factory = async_sessionmaker(
                bind=_get_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
            )
        else:
            _session_factory = lambda: LocalSQLiteAsyncSession(settings.db.sqlite_path)
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[Any, None]:
    """Context manager asincrono per una sessione database."""
    session = _get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


class _DisposeResult:
    """Awaitable result returned by `dispose_engine()` so both sync `dispose_engine()` and `await dispose_engine()` work."""

    def __init__(self, engine_to_dispose: Any) -> None:
        self._engine = engine_to_dispose

    def __await__(self):
        async def _coro() -> None:
            if self._engine is not None and hasattr(self._engine, "dispose"):
                await self._engine.dispose()
        return _coro().__await__()


def dispose_engine() -> _DisposeResult:
    """Chiude il connection pool e resetta lo stato. Supporta chiamata sia sincrona che `await`."""
    global _engine, _session_factory
    old_engine = _engine
    _engine = None
    _session_factory = None
    return _DisposeResult(old_engine)
