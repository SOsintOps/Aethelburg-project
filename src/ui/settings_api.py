"""Endpoints of the Settings page: Companies House keys (saved in the database) and general options."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import get_settings
from config.user_config import load_user_config, save_user_config, user_config_path
from src.datasources.daily import schedule
from src.datasources.storage import describe_location
from src.intelligence.risk_scorer import (
    DEFAULT_MASS_ADDRESS_THRESHOLD,
    MASS_ADDRESS_THRESHOLD_RANGE,
    mass_address_threshold_setting,
)
from src.services.app_settings import describe_ch_keys, save_ch_keys, test_ch_keys
from src.services.db_service import DatabaseService


class KeysRequest(BaseModel):
    # a field left out is not touched; an empty string removes the saved key
    api_key: str | None = None
    streaming_key: str | None = None


class GeneralRequest(BaseModel):
    backup_keep: int = Field(ge=1, le=50)
    mass_address_threshold: int = Field(
        default=DEFAULT_MASS_ADDRESS_THRESHOLD, ge=MASS_ADDRESS_THRESHOLD_RANGE[0], le=MASS_ADDRESS_THRESHOLD_RANGE[1]
    )


def build_settings_router(db: DatabaseService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings")
    async def settings_overview() -> dict[str, Any]:
        cfg = load_user_config()
        enabled, at = schedule()
        return {
            "ch_keys": describe_ch_keys(),
            "daily": {"enabled": enabled, "time": at, "documents": bool(cfg.get("documents_auto_download", False))},
            "backup_keep": int(cfg.get("backup_keep", 7)),
            "mass_address_threshold": mass_address_threshold_setting(),
            "location": describe_location(),
            "config_file": str(user_config_path()),
            "database": str(db.db_path or get_settings().db.sqlite_path),
            "version": get_settings().version,
        }

    @router.post("/api/settings/ch-keys")
    async def settings_ch_keys(req: KeysRequest) -> dict[str, Any]:
        values = req.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="No key given")
        try:
            return await asyncio.to_thread(save_ch_keys, db, values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/settings/ch-keys/test")
    async def settings_ch_keys_test() -> dict[str, Any]:
        return await test_ch_keys()

    @router.post("/api/settings/general")
    async def settings_general(req: GeneralRequest) -> dict[str, Any]:
        save_user_config({"backup_keep": req.backup_keep, "mass_address_threshold": req.mass_address_threshold})
        return {"backup_keep": req.backup_keep, "mass_address_threshold": req.mass_address_threshold}

    return router
