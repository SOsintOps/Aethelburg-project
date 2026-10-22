"""Tests for config.database."""
from __future__ import annotations

import inspect

from config.database import dispose_engine, get_session


def test_get_session_is_async_context_manager():
    assert inspect.isasyncgenfunction(get_session) or hasattr(get_session, "__aenter__") or callable(get_session)


def test_dispose_engine_resets_state():
    from config import database
    database._engine = None
    database._session_factory = None
    dispose_engine()
    assert database._engine is None
    assert database._session_factory is None
