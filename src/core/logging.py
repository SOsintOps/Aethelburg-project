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


LOG_FILENAME = "aethelburg.log"


def _add_file_handler(log_dir: Any, level: int) -> None:
    """Also write to `<data folder>/logs/aethelburg.log` (5 files x 5 MB), once per process."""
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    root = logging.getLogger()
    if log_dir is None or any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(Path(log_dir) / LOG_FILENAME, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    except OSError:
        return  # read-only or missing data folder: console logging still works
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    handler.setLevel(level)
    root.addHandler(handler)
    if root.level > level:
        root.setLevel(level)


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
    _add_file_handler(settings.paths.log_dir, level)
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
