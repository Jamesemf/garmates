"""Runtime settings, read from environment variables (prefix ``GD_``) or a ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GD_", env_file=REPO_ROOT / ".env", extra="ignore")

    # Where the SQLite database, encryption key, token caches and FIT files live.
    data_dir: Path = REPO_ROOT / "data"
    # Bind to all interfaces so other devices on the home network can reach the dashboard.
    host: str = "0.0.0.0"
    port: int = 8000
    # Built React app served by FastAPI in production mode.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # Background sync cadence; 0 disables the scheduler (manual "Sync now" still works).
    sync_interval_minutes: int = 180
    # How far back the first sync for a new person reaches.
    default_history_days: int = 365
    # Recent days are re-fetched on every sync because Garmin keeps updating them.
    resync_recent_days: int = 3
    # Pause between Garmin requests so we stay a polite client of an unpublished rate limit.
    request_spacing_seconds: float = 0.4

    session_days: int = 30
    # Set true only when serving over HTTPS (e.g. behind a reverse proxy).
    secure_cookies: bool = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'garmin-dashboard.sqlite3').as_posix()}"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def fit_dir(self) -> Path:
        return self.data_dir / "fit"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.secrets_dir, self.fit_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
