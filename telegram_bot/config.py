from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    support_contact: str = Field(min_length=3, max_length=200)
    admin_ids: list[int] = Field(default_factory=list)
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    data_dir: Path = Path("data/jobs")
    max_upload_bytes: int = Field(default=20_000_000, ge=1, le=20_000_000)
    max_image_pixels: int = Field(default=16_000_000, ge=10_000, le=40_000_000)
    cpu_concurrency: int = Field(default=2, ge=1, le=16)
    invoice_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def async_database(cls, value: str) -> str:
        if not value.startswith(("sqlite+aiosqlite://", "postgresql+asyncpg://")):
            raise ValueError("Use sqlite+aiosqlite or postgresql+asyncpg")
        return value
