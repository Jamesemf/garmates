"""Per-person access to the Garmin Personal API.

Wraps Garmin's official client (``garmin_personal_api``) with the things a long-running
multi-person sync needs: one bearer-token cache file per person, polite request spacing,
retries for transient failures and typed errors the sync can act on.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import requests
from garmin_personal_api import (
    GarminPersonalApiClient,
    GarminPersonalApiError,
    HttpError,
    PersonalApiAuthenticator,
)

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
_BACKOFF_SECONDS = (5, 20, 60)


class GarminError(Exception):
    """Base class for errors surfaced to the sync and the UI."""


class KeyRejectedError(GarminError):
    """Garmin refused the Personal API key: wrong, expired or revoked."""


class BadRequestError(GarminError):
    """HTTP 400 - for range endpoints this usually means the date span was too long."""


class RateLimitedError(GarminError):
    """Still throttled after backing off."""


class GarminConnector:
    def __init__(
        self,
        api_key: str,
        token_cache_file: Path,
        *,
        spacing_seconds: float = 0.4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._spacing = spacing_seconds
        self._sleep = sleep
        self._last_call = 0.0
        self._auth = PersonalApiAuthenticator(bearer_token_cache_file=token_cache_file)
        token = self._exchange(force=False)
        self.client = GarminPersonalApiClient(token)

    def close(self) -> None:
        self.client.close()
        self._auth.close()

    def __enter__(self) -> GarminConnector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _exchange(self, *, force: bool) -> str:
        try:
            return self._auth.obtain_token(self._api_key, force_refresh=force).access_token
        except HttpError as exc:
            if exc.status_code in (400, 401, 403):
                raise KeyRejectedError(
                    "Garmin rejected this Personal API key (it may have expired or been "
                    "revoked). Create a new key in Garmin Connect and update it here."
                ) from exc
            raise GarminError(f"Token exchange failed with HTTP {exc.status_code}") from exc
        except GarminPersonalApiError as exc:
            raise GarminError(f"Token exchange failed: {exc}") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise GarminError(f"Couldn't reach Garmin: {exc}") from exc

    def call(self, method: Callable[..., T], *args: Any, **kwargs: Any) -> T | None:
        """Invoke a ``GarminPersonalApiClient`` method with pacing and retries.

        Returns ``None`` for 404 (no data for that day/range).
        """
        refreshed = False
        attempt = 0
        while True:
            wait = self._spacing - (time.monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.monotonic()
            try:
                return method(*args, **kwargs)
            except HttpError as exc:
                status = exc.status_code
                if status == 404:
                    return None
                if status == 400:
                    raise BadRequestError(_short(exc.response_text)) from exc
                if status in (401, 403) and not refreshed:
                    refreshed = True
                    self.client.update_bearer_token(self._exchange(force=True))
                    continue
                if status in (401, 403):
                    raise KeyRejectedError(
                        "Garmin refused access with this key after a token refresh."
                    ) from exc
                if status in _TRANSIENT_STATUSES and attempt < len(_BACKOFF_SECONDS):
                    delay = _BACKOFF_SECONDS[attempt]
                    attempt += 1
                    _LOGGER.warning("Garmin HTTP %s; retrying in %ss", status, delay)
                    self._sleep(delay)
                    continue
                if status == 429:
                    raise RateLimitedError("Garmin is rate limiting requests") from exc
                raise GarminError(f"Garmin HTTP {status}: {_short(exc.response_text)}") from exc
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < len(_BACKOFF_SECONDS):
                    delay = _BACKOFF_SECONDS[attempt]
                    attempt += 1
                    _LOGGER.warning("Network error talking to Garmin (%s); retrying", exc)
                    self._sleep(delay)
                    continue
                raise GarminError(f"Network error talking to Garmin: {exc}") from exc


def _short(text: str | None, limit: int = 200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"
