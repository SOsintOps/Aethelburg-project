"""
Application settings through Pydantic v2 (pydantic-settings, or a python-dotenv fallback).

Precedence (later entries win):
  1. Defaults in this file
  2. `.env` in the project root
  3. Environment variables

Secrets left empty by the above are filled from, in order: the `app_settings` table of the
database (Companies House keys saved on the Settings page), then python-keyring.
"""
from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field, model_validator

from config.user_config import DB_FILENAME, resolve_data_dir

PROJECT_ROOT = Path(__file__).parent.parent
# Companies House key field -> name in the `app_settings` table and in the keyring
CH_KEY_NAMES = {"api_key": "ch_api_key", "streaming_key": "ch_streaming_key"}


def read_app_settings(db_path: Path | str | None, names: list[str]) -> dict[str, str]:
    """Values saved in the `app_settings` table (read-only; empty when the database or table is missing)."""
    if not db_path or not Path(db_path).exists():
        return {}
    uri = "file:" + quote(Path(db_path).resolve().as_posix(), safe="/:") + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            marks = ",".join("?" for _ in names)
            rows = conn.execute(f"SELECT key, value FROM app_settings WHERE key IN ({marks})", names).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return {key: (value or "").strip() for key, value in rows if (value or "").strip()}

try:
    from dotenv import dotenv_values
except ImportError:
    def dotenv_values(_path: Any = None) -> dict[str, str | None]:
        return {}

try:
    from pydantic_settings import BaseSettings as _PydanticBaseSettings
    from pydantic_settings import SettingsConfigDict
    HAS_PYDANTIC_SETTINGS = True
except ImportError:
    HAS_PYDANTIC_SETTINGS = False

    def SettingsConfigDict(**kwargs: Any) -> ConfigDict:  # type: ignore[misc]  # noqa: N802 - stands in for pydantic-settings
        return ConfigDict(
            extra=kwargs.get("extra", "ignore"),
            populate_by_name=kwargs.get("populate_by_name", True),
        )

    class _PydanticBaseSettings(BaseModel):  # type: ignore[no-redef]
        """Fallback BaseSettings over Pydantic v2 BaseModel reading `.env` and `os.environ`."""

        @model_validator(mode="before")
        @classmethod
        def _inject_env_vars(cls, values: Any) -> Any:
            if not isinstance(values, dict):
                return values
            merged = dict(values)
            env_file = PROJECT_ROOT / ".env"
            file_vals = dotenv_values(env_file) if env_file.exists() else {}
            for field_name, field_info in cls.model_fields.items():
                if field_name in merged:
                    continue
                # only the declared variable: `name` must not pick up $NAME, nor `user` $USER
                alias = field_info.alias or field_name.upper()
                if alias in os.environ:
                    merged[field_name] = os.environ[alias]
                elif alias in file_vals and file_vals[alias] is not None:
                    merged[field_name] = file_vals[alias]
            return merged


BaseSettings = _PydanticBaseSettings


class DatabaseSettings(BaseSettings):
    backend: str = Field(default="auto", alias="DB_BACKEND")  # auto | postgresql | sqlite
    host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    name: str = Field(default="aethelburg", alias="POSTGRES_DB")
    user: str = Field(default="aethelburg", alias="POSTGRES_USER")
    password: str = Field(default="", alias="POSTGRES_PASSWORD")
    ssl_mode: str = Field(default="prefer", alias="POSTGRES_SSLMODE")
    # None = `<data_dir>/aethelburg.sqlite`, filled in by `Settings`
    sqlite_path: Path | None = Field(default=None, alias="SQLITE_PATH")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def async_url(self) -> str:
        """Async URL for SQLAlchemy + asyncpg (without sslmode, a libpq parameter asyncpg rejects)."""
        if self.backend == "sqlite":
            return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"
        return (
            f"postgresql+asyncpg://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @computed_field
    @property
    def sync_url(self) -> str:
        """Sync URL for Alembic migrations and batch jobs."""
        if self.backend == "sqlite":
            return f"sqlite:///{self.sqlite_path.as_posix()}"
        return (
            f"postgresql+psycopg2://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}?sslmode={self.ssl_mode}"
        )


class NominatimSettings(BaseSettings):
    url: str = Field(
        default="http://127.0.0.1:8080",
        alias="NOMINATIM_URL",
    )
    enabled: bool = Field(default=False, alias="NOMINATIM_ENABLED")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class CompaniesHouseSettings(BaseSettings):
    api_key: str = Field(default="", alias="CH_API_KEY")
    streaming_key: str = Field(default="", alias="CH_STREAMING_KEY")
    api_base_url: str = "https://api.company-information.service.gov.uk"
    streaming_base_url: str = "https://stream.companieshouse.gov.uk"
    rate_limit: int = 600
    rate_window: int = 300
    # where each key came from: environment, database, keyring (filled by Settings.resolve_ch_keys)
    _key_sources: dict[str, str] = PrivateAttr(default_factory=dict)

    @property
    def key_sources(self) -> dict[str, str]:
        return self._key_sources

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def base_url(self) -> str:
        return self.api_base_url


class PathSettings(BaseSettings):
    # DATA_DIR (env/.env) > user config.toml > legacy <project>/dati with a database > C:\AethelburgData
    data_dir: Path = Field(default_factory=resolve_data_dir, alias="DATA_DIR")
    # None = derived from data_dir by `Settings`
    onspd_path: Path | None = Field(default=None, alias="ONSPD_PATH")
    log_dir: Path | None = None

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(BaseSettings):
    env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    ui_host: str = Field(default="127.0.0.1", alias="AETHELBURG_HOST")
    ui_port: int = Field(default=8050, alias="AETHELBURG_PORT")
    version: str = "0.3.0-beta.1"
    ontology_version: str = "3.x-ftm"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    """Main Aethelburg settings."""

    app: AppSettings = Field(default_factory=AppSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    nominatim: NominatimSettings = Field(default_factory=NominatimSettings)
    ch: CompaniesHouseSettings = Field(default_factory=CompaniesHouseSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def app_name(self) -> str:
        return "Aethelburg"

    @property
    def version(self) -> str:
        return self.app.version

    @property
    def data_dir(self) -> Path:
        return self.paths.data_dir

    @property
    def ch_api(self) -> CompaniesHouseSettings:
        return self.ch

    @model_validator(mode="after")
    def _derive_data_paths(self) -> Settings:
        """Database, logs and ONSPD live under the data folder unless set explicitly."""
        data_dir = self.paths.data_dir
        if self.db.sqlite_path is None:
            self.db.sqlite_path = data_dir / DB_FILENAME
        if self.paths.log_dir is None:
            self.paths.log_dir = data_dir / "logs"
        if self.paths.onspd_path is None:
            self.paths.onspd_path = data_dir / "onspd" / "ONSPD_latest.csv"
        return self

    def resolve_ch_keys(self, db_path: Path | str | None = None) -> None:
        """Companies House keys: environment, else the Settings page (database), else the keyring.

        Called again after the Settings page saves a key; keys set in the environment are kept.
        """
        sources = {
            f: "environment"
            for f in CH_KEY_NAMES
            if self.ch.key_sources.get(f, "environment") == "environment" and getattr(self.ch, f)
        }
        for field in CH_KEY_NAMES:
            if field not in sources:
                setattr(self.ch, field, "")
        missing = [f for f in CH_KEY_NAMES if f not in sources]
        stored = read_app_settings(db_path or self.db.sqlite_path, [CH_KEY_NAMES[f] for f in missing]) if missing else {}
        for field in missing:
            value = stored.get(CH_KEY_NAMES[field], "")
            if not value:
                try:
                    import keyring

                    value = (keyring.get_password("aethelburg", CH_KEY_NAMES[field]) or "").strip()
                    source = "keyring"
                except Exception:  # keyring missing or no backend
                    value = ""
            else:
                source = "database"
            if value:  # a pasted key often carries a space or newline: stripped above
                setattr(self.ch, field, value)
                sources[field] = source
        self.ch._key_sources = sources

    @model_validator(mode="after")
    def _load_keyring_and_validate(self) -> Settings:
        """
        1. Load the database password from python-keyring and the Companies House keys
           (`resolve_ch_keys`) when the environment does not set them.
        2. Require a database password outside development when the backend is not SQLite.
        """
        try:
            import keyring

            if not self.db.password:
                stored = keyring.get_password("aethelburg", "postgres")
                if stored:
                    self.db.password = stored
        except ImportError:
            pass
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("keyring error: %s", e)
        self.resolve_ch_keys()

        effective_env = os.environ.get("APP_ENV") or self.app.env
        if (
            self.db.backend != "sqlite"
            and not self.db.password
            and effective_env != "development"
        ):
            raise ValueError("POSTGRES_PASSWORD must be set in non-development environments")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings singleton, cached after the first call."""
    return Settings()
