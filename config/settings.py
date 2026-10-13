"""
Configurazione applicazione via Pydantic Settings v2.

Ordine di precedenza (dal basso = maggiore priorità):
  1. Valori default in questo file
  2. File .env nella root del progetto
  3. Variabili d'ambiente del sistema
  4. python-keyring per secrets sensibili (password DB)
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent


class DatabaseSettings(BaseSettings):
    host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    name: str = Field(default="aethelburg", alias="POSTGRES_DB")
    user: str = Field(default="aethelburg", alias="POSTGRES_USER")
    password: str = Field(default="", alias="POSTGRES_PASSWORD")
    ssl_mode: str = Field(default="prefer", alias="POSTGRES_SSLMODE")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _validate_password(self) -> "DatabaseSettings":
        if not self.password and os.environ.get("APP_ENV", "development") != "development":
            raise ValueError("POSTGRES_PASSWORD must be set in non-development environments")
        return self

    @computed_field
    @property
    def async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}?sslmode={self.ssl_mode}"
        )

    @computed_field
    @property
    def sync_url(self) -> str:
        """URL sincrono per Alembic migrations."""
        return (
            f"postgresql+psycopg2://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.name}?sslmode={self.ssl_mode}"
        )


class NominatimSettings(BaseSettings):
    url: str = Field(
        default="http://127.0.0.1:8080/nominatim",
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

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


class PathSettings(BaseSettings):
    data_dir: Path = Field(default=PROJECT_ROOT / "dati", alias="DATA_DIR")
    onspd_path: Path = Field(
        default=PROJECT_ROOT / "dati" / "onspd" / "ONSPD_latest.csv",
        alias="ONSPD_PATH",
    )
    log_dir: Path = PROJECT_ROOT / "logs"

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
    version: str = "0.1.0"
    ontology_version: str = "1.0.0"

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

    @model_validator(mode="after")
    def _load_keyring_secrets(self) -> "Settings":
        """
        Carica secrets sensibili da python-keyring se non già impostati via env.
        Keyring usa Windows Credential Manager su Windows.
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
            pass  # keyring not installed
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("keyring error: %s", e)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings — cached dopo il primo accesso."""
    return Settings()
