"""Structured logging configuration using structlog (with stdlib keyword-aware fallback)."""
from __future__ import annotations

import logging
import sys
from typing import Any


class _KeyValueLoggerAdapter:
    """Stdlib logger wrapper that accepts structlog-style keyword arguments (`log.info('event', k=v)`)."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _fmt(self, event: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return str(event)
        kv_str = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return f"{event} [{kv_str}]"

    def debug(self, event: str, **kwargs: Any) -> None:
        self._logger.debug(self._fmt(event, kwargs))

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info(self._fmt(event, kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning(self._fmt(event, kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        self._logger.error(self._fmt(event, kwargs))

    def exception(self, event: str, **kwargs: Any) -> None:
        self._logger.exception(self._fmt(event, kwargs))


def get_logger(name: str = "aethelburg") -> Any:
    """Return a structlog logger if installed, or a keyword-aware stdlib logger adapter."""
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return _KeyValueLoggerAdapter(logging.getLogger(name))


def setup_logging(log_level: str | None = None) -> None:
    """Configure structlog (if installed) and stdlib logging."""
    from config.settings import get_settings

    settings = get_settings()
    effective_level_str = (log_level or settings.app.log_level or "INFO").upper()
    level = getattr(logging, effective_level_str, logging.INFO)
    is_dev = settings.app.env == "development"

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
        level=level,
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        import structlog

        shared_processors: list[Any] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
        ]

        if is_dev:
            renderer: Any = structlog.dev.ConsoleRenderer()
        else:
            renderer = structlog.processors.JSONRenderer()

        structlog.configure(
            processors=[*shared_processors, renderer],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    except ImportError:
        pass
