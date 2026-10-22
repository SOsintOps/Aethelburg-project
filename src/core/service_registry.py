"""Service availability registry — singleton with listener/signal notifications (ADR-009)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from config.database import get_session, get_sqlite_connection
from config.settings import get_settings


class ServiceRegistry:
    """Tracks availability of external and local services (PostgreSQL, SQLite, Nominatim, ONSPD)."""

    _instance: ServiceRegistry | None = None

    def __new__(cls) -> ServiceRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._status: dict[str, str] = {
                "postgresql": "checking",
                "sqlite": "checking",
                "nominatim": "checking",
                "onspd": "available",
            }
            cls._instance._listeners: list[Callable[[dict[str, str]], Any]] = []
        return cls._instance

    @property
    def status(self) -> dict[str, str]:
        return dict(self._status)

    def subscribe(self, callback: Callable[[dict[str, str]], Any]) -> None:
        """Register a listener notified whenever service availability changes (ADR-009)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[dict[str, str]], Any]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        snapshot = self.status
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    def is_available(self, service: str) -> bool:
        return self._status.get(service) == "available"

    async def check_all(self) -> dict[str, str]:
        await self._check_postgresql()
        await self._check_sqlite()
        await self._check_nominatim()
        self._notify()
        return self.status

    async def _check_postgresql(self) -> None:
        from config.database import HAS_SQLALCHEMY
        settings = get_settings()
        if settings.db.backend in ("sqlite", "auto") and not HAS_SQLALCHEMY:
            self._status["postgresql"] = "standby (sqlite active)"
            return
        if settings.db.backend == "sqlite":
            self._status["postgresql"] = "standby (sqlite active)"
            return
        try:
            async with get_session() as session:
                await session.execute("SELECT 1")
            self._status["postgresql"] = "available"
        except Exception:
            self._status["postgresql"] = "unavailable"

    async def _check_sqlite(self) -> None:
        try:
            conn = get_sqlite_connection()
            conn.execute("SELECT 1")
            conn.close()
            self._status["sqlite"] = "available"
        except Exception:
            self._status["sqlite"] = "unavailable"

    async def _check_nominatim(self) -> None:
        settings = get_settings()
        if not settings.nominatim.enabled:
            self._status["nominatim"] = "unavailable"
            return
        base_url = settings.nominatim.url.rstrip("/")
        if base_url.endswith("/nominatim"):
            base_url = base_url[: -len("/nominatim")]
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{base_url}/status")
                self._status["nominatim"] = "available" if r.status_code == 200 else "unavailable"
        except Exception:
            self._status["nominatim"] = "unavailable"
