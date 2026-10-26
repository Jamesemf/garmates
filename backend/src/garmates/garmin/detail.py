"""On-demand detail that is too heavy to bulk-sync: activity tracks and intraday day views.

Results are cached in the database; finished days/activities are never fetched twice.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
from typing import Any

import fitdecode

from ..config import get_settings
from ..db import session_scope
from ..models import Activity, ActivityTrack, RawPayload, utcnow
from . import parsers
from .sync import open_connector, store_raw

MAX_TRACK_POINTS = 1500
_SEMICIRCLE_TO_DEG = 180 / 2**31
# Today's (and yesterday's) intraday data keeps changing; refresh it after this long.
_LIVE_CACHE_MINUTES = 30


def decode_fit(data: bytes) -> list[list[float | None]]:
    """Return downsampled ``[elapsed_s, lat, lon, hr, altitude_m, speed_mps, distance_m]``."""
    if data[:2] == b"PK":  # Garmin serves the original file inside a ZIP
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            fit_names = [n for n in archive.namelist() if n.lower().endswith(".fit")]
            if not fit_names:
                return []
            data = archive.read(fit_names[0])

    points: list[list[float | None]] = []
    start: dt.datetime | None = None
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                continue
            values = {f.name: f.value for f in frame.fields}
            timestamp = values.get("timestamp")
            if not isinstance(timestamp, dt.datetime):
                continue
            start = start or timestamp
            lat, lon = values.get("position_lat"), values.get("position_long")
            altitude = values.get("enhanced_altitude", values.get("altitude"))
            speed = values.get("enhanced_speed", values.get("speed"))
            points.append(
                [
                    round((timestamp - start).total_seconds()),
                    round(lat * _SEMICIRCLE_TO_DEG, 6) if isinstance(lat, int) else None,
                    round(lon * _SEMICIRCLE_TO_DEG, 6) if isinstance(lon, int) else None,
                    values.get("heart_rate"),
                    round(altitude, 1) if isinstance(altitude, int | float) else None,
                    round(speed, 2) if isinstance(speed, int | float) else None,
                    round(values["distance"], 1)
                    if isinstance(values.get("distance"), int | float)
                    else None,
                ]
            )
    if len(points) > MAX_TRACK_POINTS:
        step = len(points) / MAX_TRACK_POINTS
        points = [points[int(i * step)] for i in range(MAX_TRACK_POINTS)] + [points[-1]]
    return points


def get_activity_track(activity_id: int) -> dict[str, Any]:
    with session_scope() as db:
        cached = db.get(ActivityTrack, activity_id)
        if cached is not None and cached.error is None:
            return {"points": cached.points or [], "error": None}
        activity = db.get(Activity, activity_id)
        if activity is None:
            raise LookupError("Unknown activity")
        person_id = activity.person_id

    settings = get_settings()
    error = None
    points: list = []
    try:
        with open_connector(person_id) as conn:
            data = conn.call(conn.client.download_activity, activity_id)
        if data:
            (settings.fit_dir / f"{person_id}-{activity_id}.zip").write_bytes(data)
            points = decode_fit(data)
    except Exception as exc:  # network, key or FIT decode problems are all reported to the UI
        error = str(exc) or exc.__class__.__name__

    with session_scope() as db:
        track = db.get(ActivityTrack, activity_id) or ActivityTrack(activity_id=activity_id)
        track.points, track.error, track.fetched_at = points, error, utcnow()
        db.add(track)
    return {"points": points, "error": error}


def _cached_payload(person_id: int, dataset: str, day: dt.date) -> tuple[bool, Any]:
    with session_scope() as db:
        raw = db.query(RawPayload).filter_by(
            person_id=person_id, dataset=dataset, key=day.isoformat()
        ).one_or_none()
        if raw is None:
            return False, None
        is_settled = day < dt.date.today() - dt.timedelta(days=1)
        fresh = utcnow() - raw.fetched_at < dt.timedelta(minutes=_LIVE_CACHE_MINUTES)
        return (is_settled or fresh), json.loads(raw.payload)


def get_day_detail(person_id: int, day: dt.date, *, allow_fetch: bool = True) -> dict[str, Any]:
    """Intraday heart rate and Body Battery for one person and day."""
    wanted = {
        "day_heart_rate": lambda c: c.call(c.client.get_daily_heart_rate, day),
        "day_body_battery": lambda c: c.call(c.client.get_daily_body_battery, day, day),
    }
    payloads: dict[str, Any] = {}
    missing = []
    for dataset in wanted:
        usable, payload = _cached_payload(person_id, dataset, day)
        payloads[dataset] = payload
        if not usable:
            missing.append(dataset)

    error = None
    if missing and allow_fetch:
        try:
            with open_connector(person_id) as conn:
                fetched = {name: wanted[name](conn) for name in missing}
            with session_scope() as db:
                for name, payload in fetched.items():
                    if payload is not None:
                        store_raw(db, person_id, name, day.isoformat(), payload)
                    payloads[name] = payload
        except Exception as exc:  # serve whatever is cached, report the problem
            error = str(exc)

    return {
        "heart_rate": parsers.parse_heart_rate_series(payloads.get("day_heart_rate")),
        "body_battery": parsers.parse_body_battery_series(payloads.get("day_body_battery")),
        "error": error,
    }
