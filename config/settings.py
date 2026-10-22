"""
Configurazione applicazione via Pydantic v2 (+ pydantic-settings o python-dotenv fallback).

Ordine di precedenza (dal basso = maggiore priorità):
  1. Valori default in questo file
  2. File .env nella root del progetto
  3. Variabili d'ambiente del sistema
  4. python-keyring per secrets sensibili (password DB, API key)
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from config.user_config import DB_FILENAME, resolve_data_dir

PROJECT_ROOT = Path(__file__).parent.parent

try:
    from dotenv import dotenv_values
except ImportError:
    def dotenv_values(_path: Any = None) -> dict[str, str | None]:
        return {}

try:
    from pydantic_settings import BaseSettings as _PydanticBaseSettings, SettingsConfigDict
    HAS_PYDANTIC_SETTINGS = True
except ImportError:
    HAS_PYDANTIC_SETTINGS = False

    def SettingsConfigDict(**kwargs: Any) -> ConfigDict:  # type: ignore[misc]
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
                alias = field_info.alias or field_name
                if alias in os.environ:
                    merged[field_name] = os.environ[alias]
                elif field_name.upper() in os.environ:
                    merged[field_name] = os.environ[field_name.upper()]
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
        populate_by_name=True,
    )

    @computed_field
    @property
    def async_url(self) -> str:
        """URL asincrono per SQLAlchemy + asyncpg (senza sslmode, parametro libpq non valido in asyncpg)."""
        if self.backend == "sqlite":
            return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"
        return (
            f"postgresql+asyncpg://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @computed_field
    @property
    def sync_url(self) -> str:
        """URL sincrono per Alembic migrations e operazioni batch."""
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
        populate_by_name=True,
    )


class CompaniesHouseSettings(BaseSettings):
    api_key: str = Field(default="", alias="CH_API_KEY")
    streaming_key: str = Field(default="", alias="CH_STREAMING_KEY")
    api_base_url: str = "https://api.company-information.service.gov.uk"
    streaming_base_url: str = "https://stream.companieshouse.gov.uk"
    rate_limit: int = 600
    rate_window: int = 300

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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
        populate_by_name=True,
    )


class AppSettings(BaseSettings):
    env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    ui_host: str = Field(default="127.0.0.1", alias="AETHELBURG_HOST")
    ui_port: int = Field(default=8050, alias="AETHELBURG_PORT")
    version: str = "0.2.0-beta.1"
    ontology_version: str = "3.x-ftm"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


class Settings(BaseSettings):
    """Configurazione principale Aethelburg."""

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
    def _derive_data_paths(self) -> "Settings":
        """Database, logs and ONSPD live under the data folder unless set explicitly."""
        data_dir = self.paths.data_dir
        if self.db.sqlite_path is None:
            self.db.sqlite_path = data_dir / DB_FILENAME
        if self.paths.log_dir is None:
            self.paths.log_dir = data_dir / "logs"
        if self.paths.onspd_path is None:
            self.paths.onspd_path = data_dir / "onspd" / "ONSPD_latest.csv"
        return self

    @model_validator(mode="after")
    def _load_keyring_and_validate(self) -> "Settings":
        """
        1. Carica secrets sensibili da python-keyring se non già impostati via env.
        2. Valida la password DB in ambienti non-development quando il backend non è sqlite.
        """
        try:
            import keyring

            if not self.db.password:
                stored = keyring.get_password("aethelburg", "postgres")
                if stored:
                    self.db.password = stored

            if not self.ch.api_key:
                stored = keyring.get_password("aethelburg", "ch_api_key")
                if stored:
                    self.ch.api_key = stored
        except ImportError:
            pass
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("keyring error: %s", e)

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
    """Singleton settings — cached dopo il primo accesso."""
    return Settings()
