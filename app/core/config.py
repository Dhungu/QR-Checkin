from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_DEV_SECRET = "dev-only-secret-change-me-please-0123456789"
_DEV_ADMIN_KEY = "dev-admin-key"
_DEV_STAFF_KEY = "dev-staff-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "QR Event Check-In"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    base_url: str = "http://localhost:8000"

    database_url: str = "sqlite+aiosqlite:///./dev.db"
    # Dev convenience. In production, run `alembic upgrade head` instead.
    auto_create_tables: bool = True

    # Secrets
    qr_hmac_secret: str = _DEV_SECRET
    admin_api_key: str = _DEV_ADMIN_KEY  # organizers
    staff_api_key: str = _DEV_STAFF_KEY  # gate staff

    # Behaviour
    rate_limit_per_minute: int = 120
    checkin_grace_minutes: int = 0  # allow scans this long before start / after end
    max_upload_bytes: int = 5_000_000

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> "Settings":
        if self.environment == "production":
            problems = []
            if self.qr_hmac_secret == _DEV_SECRET or len(self.qr_hmac_secret) < 32:
                problems.append("QR_HMAC_SECRET must be a random string of 32+ characters")
            if self.admin_api_key == _DEV_ADMIN_KEY or len(self.admin_api_key) < 16:
                problems.append("ADMIN_API_KEY must be changed (16+ characters)")
            if self.staff_api_key == _DEV_STAFF_KEY or len(self.staff_api_key) < 16:
                problems.append("STAFF_API_KEY must be changed (16+ characters)")
            if problems:
                raise ValueError("Insecure production config: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
