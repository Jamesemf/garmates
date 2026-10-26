"""Runtime settings, read from environment variables (prefix ``GARMATES_``) or a ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DATABASE_FILE = "garmates.sqlite3"
# Name used before the project was renamed; adopted automatically by ensure_dirs().
LEGACY_DATABASE_FILE = "garmin-dashboard.sqlite3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GARMATES_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

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

    # Fernet key for stored Garmin API keys. Unset: one is generated in
    # data/secrets/master.key on first run (back it up with the database).
    secret_key: str | None = None

    session_days: int = 30
    # Set true only when serving over HTTPS (e.g. behind a reverse proxy).
    secure_cookies: bool = False
    # Behind a reverse proxy (Caddy): honour X-Forwarded-For/-Proto so login rate limiting
    # sees each device's address. Only enable when the app isn't reachable directly.
    trust_proxy: bool = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / DATABASE_FILE).as_posix()}"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def fit_dir(self) -> Path:
        return self.data_dir / "fit"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.secrets_dir, self.fit_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._adopt_legacy_database()

    def _adopt_legacy_database(self) -> None:
        """Rename a database created under the old name (with its WAL files) to the new one."""
        current = self.data_dir / DATABASE_FILE
        legacy = self.data_dir / LEGACY_DATABASE_FILE
        if current.exists() or not legacy.exists():
            return
        for suffix in ("-wal", "-shm", ""):
            old = legacy.with_name(legacy.name + suffix)
            if old.exists():
                old.rename(current.with_name(current.name + suffix))


@lru_cache
def get_settings() -> Settings:
    return Settings()
