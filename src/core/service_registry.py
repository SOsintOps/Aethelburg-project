"""Service availability registry — singleton."""
from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text

from config.database import get_session
from config.settings import get_settings


class ServiceRegistry:
    """Tracks availability of external services (DB, Nominatim)."""

    _instance: ServiceRegistry | None = None

    def __new__(cls) -> ServiceRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._status: dict[str, str] = {
                "postgresql": "checking",
                "nominatim": "checking",
            }
        return cls._instance

    @property
    def status(self) -> dict[str, str]:
        return dict(self._status)

    def is_available(self, service: str) -> bool:
        return self._status.get(service) == "available"

    async def check_all(self) -> dict[str, str]:
        await self._check_postgresql()
        await self._check_nominatim()
        return self.status

    async def _check_postgresql(self) -> None:
        try:
            async with get_session() as session:
                await session.execute(text("SELECT 1"))
            self._status["postgresql"] = "available"
        except Exception:
            self._status["postgresql"] = "unavailable"

    async def _check_nominatim(self) -> None:
        settings = get_settings()
        if not settings.nominatim.enabled:
            self._status["nominatim"] = "unavailable"
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{settings.nominatim.url}/status")
                self._status["nominatim"] = "available" if r.status_code == 200 else "unavailable"
        except Exception:
            self._status["nominatim"] = "unavailable"
