"""Display preferences: units, week start and clock format.

Preferences belong to the *viewer*: everyone's data is shown in the signed-in person's
units. Stored values are always metric; the UI converts for display. Effective
preferences are the person's own choices, then what their Garmin profile says, then
metric defaults.
"""

from __future__ import annotations

from typing import Any

OPTIONS: dict[str, tuple[str, ...]] = {
    "distance": ("km", "mi"),
    "weight": ("kg", "lb", "st"),
    "volume": ("ml", "floz"),
    "elevation": ("m", "ft"),
    "week_start": ("monday", "sunday"),
    "time_format": ("24h", "12h"),
}

DEFAULTS: dict[str, str] = {
    "distance": "km",
    "weight": "kg",
    "volume": "ml",
    "elevation": "m",
    "week_start": "monday",
    "time_format": "24h",
}

_SYSTEMS = {
    "metric": {"distance": "km", "weight": "kg", "volume": "ml", "elevation": "m"},
    "statute_us": {"distance": "mi", "weight": "lb", "volume": "floz", "elevation": "ft"},
    "statute_uk": {"distance": "mi", "weight": "st", "volume": "ml", "elevation": "ft"},
}


def validate(values: dict[str, Any]) -> dict[str, str]:
    """Keep only known keys with allowed values; raise on anything else."""
    clean = {}
    for key, value in values.items():
        if key not in OPTIONS:
            raise ValueError(f"Unknown preference {key!r}")
        if value is None:
            continue
        if value not in OPTIONS[key]:
            raise ValueError(f"{key} must be one of {OPTIONS[key]}")
        clean[key] = value
    return clean


def from_garmin_profile(profile: Any) -> dict[str, str]:
    """Map Garmin's user profile settings onto our preference keys (best effort)."""
    if not isinstance(profile, dict):
        return {}
    derived: dict[str, str] = {}
    system = str(profile.get("measurementSystem") or "").lower()
    derived.update(_SYSTEMS.get(system, {}))

    first_day = profile.get("firstDayOfWeek")
    day_name = first_day.get("dayName") if isinstance(first_day, dict) else first_day
    if isinstance(day_name, str) and day_name.lower() in OPTIONS["week_start"]:
        derived["week_start"] = day_name.lower()

    time_format = profile.get("timeFormat")
    key = time_format.get("formatKey") if isinstance(time_format, dict) else time_format
    if isinstance(key, str):
        key = key.lower()
        if "twelve" in key or "12" in key:
            derived["time_format"] = "12h"
        elif "twenty" in key or "24" in key:
            derived["time_format"] = "24h"
    return derived


def effective(own: dict | None, garmin: dict | None) -> dict[str, str]:
    result = dict(DEFAULTS)
    for source in (garmin or {}, own or {}):
        for key, value in source.items():
            if key in OPTIONS and value in OPTIONS[key]:
                result[key] = value
    return result
