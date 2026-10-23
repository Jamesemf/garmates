"""Turn Garmin Personal API JSON into rows for the normalised tables.

Field names follow Garmin's published OpenAPI spec for the Personal API. Parsers are
deliberately forgiving: missing objects, sentinel values (Garmin uses negative numbers for
"not enough data") and unit quirks become ``None`` rather than errors, so one odd day
never breaks a sync.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

Row = dict[str, Any]


# --- helpers -------------------------------------------------------------------------------


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _num(value: Any, *, allow_zero: bool = True) -> float | None:
    """Numeric value, or None for missing/sentinel values (Garmin uses -1/-2 for 'no data')."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or (number == 0 and not allow_zero):
        return None
    return number


def _int(value: Any, *, allow_zero: bool = True) -> int | None:
    number = _num(value, allow_zero=allow_zero)
    return None if number is None else round(number)


def _minutes(millis: Any) -> float | None:
    number = _num(millis)
    return None if number is None else round(number / 60000, 1)


def parse_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_timestamp(value: Any) -> dt.datetime | None:
    """Garmin timestamps come as epoch millis (int or numeric string) or ISO strings.

    "Local" timestamps are wall-clock times encoded as if they were UTC, so we keep them naive.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        try:
            return dt.datetime.fromtimestamp(float(value) / 1000, dt.UTC).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo is None else (
            parsed.astimezone(dt.UTC).replace(tzinfo=None)
        )
    return None


def _kg(value: Any) -> float | None:
    """Weights are documented as kg, but Garmin Connect historically used grams."""
    number = _num(value, allow_zero=False)
    if number is None:
        return None
    return round(number / 1000, 2) if number > 500 else round(number, 2)


# --- daily summaries -----------------------------------------------------------------------


def parse_daily_summaries(payload: Any) -> list[Row]:
    items = payload.get("data") if isinstance(payload, dict) else payload
    rows: dict[dt.date, Row] = {}
    for item in items or []:
        day = parse_date(_get(item, "calendarDate"))
        if day is None:
            continue
        hydration_goal = _get(item, "hydration", "goalInFractionalMl")
        if hydration_goal is None:
            hydration_goal = _get(item, "hydration", "goalInMl")
        rows[day] = {
            "date": day,
            "steps": _int(_get(item, "movement", "steps", "value")),
            "step_goal": _int(_get(item, "movement", "steps", "goal"), allow_zero=False),
            "distance_m": _num(_get(item, "movement", "steps", "distanceInMeters")),
            "floors_up": _int(_get(item, "movement", "floorsAscended", "value")),
            "floors_goal": _int(_get(item, "movement", "floorsAscended", "goal"), allow_zero=False),
            "calories_total": _int(_get(item, "calories", "burnedTotal"), allow_zero=False),
            "calories_active": _int(_get(item, "calories", "burnedActive")),
            "calories_resting": _int(_get(item, "calories", "burnedResting"), allow_zero=False),
            "calories_consumed": _int(_get(item, "calories", "consumedValue"), allow_zero=False),
            "rhr": _int(_get(item, "heartRate", "restingValue"), allow_zero=False),
            "hr_min": _int(_get(item, "heartRate", "minValue"), allow_zero=False),
            "hr_max": _int(_get(item, "heartRate", "maxValue"), allow_zero=False),
            "intensity_moderate": _int(_get(item, "intensityMinutes", "moderate")),
            "intensity_vigorous": _int(_get(item, "intensityMinutes", "vigorous")),
            "intensity_goal_weekly": _int(
                _get(item, "intensityMinutes", "goal"), allow_zero=False
            ),
            "stress_avg": _int(_get(item, "stress", "avgLevel")),
            "stress_max": _int(_get(item, "stress", "maxLevel")),
            "stress_qualifier": _get(item, "stress", "qualifier"),
            "stress_rest_min": _minutes(_get(item, "stress", "restDurationInMillis")),
            "stress_low_min": _minutes(_get(item, "stress", "lowStressDurationInMillis")),
            "stress_medium_min": _minutes(_get(item, "stress", "mediumStressDurationInMillis")),
            "stress_high_min": _minutes(_get(item, "stress", "highStressDurationInMillis")),
            "bb_min": _int(_get(item, "bodyBattery", "minValue"), allow_zero=False),
            "bb_max": _int(_get(item, "bodyBattery", "maxValue"), allow_zero=False),
            "bb_charged": _int(_get(item, "bodyBattery", "chargedValue")),
            "bb_drained": _int(_get(item, "bodyBattery", "drainedValue")),
            "hydration_ml": _num(_get(item, "hydration", "consumedInFractionalMl")),
            "hydration_goal_ml": _num(hydration_goal, allow_zero=False),
            "resp_avg": _int(_get(item, "respiration", "avgValue"), allow_zero=False),
            "resp_min": _int(_get(item, "respiration", "minValue"), allow_zero=False),
            "resp_max": _int(_get(item, "respiration", "maxValue"), allow_zero=False),
            "spo2_avg": _int(_get(item, "pulseOx", "avgValue"), allow_zero=False),
            "spo2_min": _int(_get(item, "pulseOx", "minValue"), allow_zero=False),
        }
    return list(rows.values())


# --- sleep ---------------------------------------------------------------------------------


def _sleep_row(item: Any) -> Row | None:
    day = parse_date(_get(item, "calendarDate"))
    if day is None:
        return None
    duration = _int(_get(item, "sleepTimeSeconds"), allow_zero=False)
    scores = _get(item, "sleepScores") or {}
    overall = scores.get("overall") or scores.get("overallScore") or {}
    score = _int(_get(overall, "value"), allow_zero=False)
    if duration is None and score is None:
        return None  # Garmin returns placeholder entries for nights without sleep data
    components = {
        name: _get(component, "value")
        for name, component in scores.items()
        if isinstance(component, dict) and _get(component, "value") is not None
    }
    return {
        "date": day,
        "score": score,
        "score_qualifier": _get(overall, "qualifierKey"),
        "duration_s": duration,
        "deep_s": _int(_get(item, "deepSleepSeconds")),
        "light_s": _int(_get(item, "lightSleepSeconds")),
        "rem_s": _int(_get(item, "remSleepSeconds")),
        "awake_s": _int(_get(item, "awakeSleepSeconds")),
        "nap_s": _int(_get(item, "napTimeSeconds")),
        "start_local": parse_timestamp(_get(item, "sleepStartTimestampLocal")),
        "end_local": parse_timestamp(_get(item, "sleepEndTimestampLocal")),
        "avg_hr": _num(_get(item, "avgHeartRate"), allow_zero=False),
        "avg_resp": _num(_get(item, "averageRespirationValue"), allow_zero=False),
        "avg_spo2": _num(_get(item, "averageSpO2Value"), allow_zero=False),
        "lowest_spo2": _int(_get(item, "lowestSpO2Value"), allow_zero=False),
        "avg_stress": _num(_get(item, "avgSleepStress")),
        "awake_count": _int(_get(item, "awakeCount")),
        "feedback": _get(item, "sleepScoreFeedback"),
        "component_scores": components or None,
    }


def parse_sleep_summaries(payload: Any) -> list[Row]:
    items = payload if isinstance(payload, list) else [payload] if payload else []
    rows = [_sleep_row(item) for item in items]
    return [row for row in rows if row is not None]


# --- HRV -----------------------------------------------------------------------------------


def parse_hrv_summaries(payload: Any) -> list[Row]:
    if isinstance(payload, dict) and "hrvSummaries" in payload:
        items = payload.get("hrvSummaries") or []
    elif isinstance(payload, dict) and "hrvSummary" in payload:
        items = [payload["hrvSummary"]]
    else:
        items = payload or []
    rows = []
    for item in items:
        day = parse_date(_get(item, "calendarDate"))
        if day is None:
            continue
        row = {
            "date": day,
            "last_night_avg": _int(_get(item, "lastNightAvg"), allow_zero=False),
            "last_night_5min_high": _int(_get(item, "lastNight5MinHigh"), allow_zero=False),
            "weekly_avg": _int(_get(item, "weeklyAvg"), allow_zero=False),
            "baseline_low_upper": _int(_get(item, "baseline", "lowUpper"), allow_zero=False),
            "baseline_balanced_low": _int(
                _get(item, "baseline", "balancedLow"), allow_zero=False
            ),
            "baseline_balanced_upper": _int(
                _get(item, "baseline", "balancedUpper"), allow_zero=False
            ),
            "status": _get(item, "status"),
        }
        if row["last_night_avg"] is None and row["weekly_avg"] is None:
            continue
        rows.append(row)
    return rows


# --- weight --------------------------------------------------------------------------------


def parse_weight_range(payload: Any) -> list[Row]:
    rows = []
    for summary in _get(payload, "dailyWeightSummaries") or []:
        day = parse_date(_get(summary, "summaryDate"))
        latest = _get(summary, "latestWeight")
        if not isinstance(latest, dict):
            entries = _get(summary, "allWeightMetrics") or []
            latest = entries[-1] if entries else None
        if day is None or not isinstance(latest, dict):
            continue
        weight = _kg(_get(latest, "weight"))
        if weight is None:
            continue
        rows.append(
            {
                "date": day,
                "weight_kg": weight,
                "bmi": _num(_get(latest, "bmi"), allow_zero=False),
                "body_fat_pct": _num(_get(latest, "bodyFat"), allow_zero=False),
                "body_water_pct": _num(_get(latest, "bodyWater"), allow_zero=False),
                "muscle_mass_kg": _kg(_get(latest, "muscleMass")),
                "bone_mass_kg": _kg(_get(latest, "boneMass")),
            }
        )
    return rows


# --- fitness age ---------------------------------------------------------------------------


def parse_fitness_age(payload: Any, as_of: dt.date) -> list[Row]:
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        return []
    fitness_age = _num(_get(item, "fitnessAge"), allow_zero=False)
    if fitness_age is None:
        return []
    return [
        {
            "date": as_of,
            "fitness_age": round(fitness_age, 1),
            "chronological_age": _int(_get(item, "chronologicalAge"), allow_zero=False),
            "achievable_fitness_age": _num(_get(item, "achievableFitnessAge"), allow_zero=False),
        }
    ]


# --- activities ----------------------------------------------------------------------------

_SPORT_KEYWORDS = (
    ("run", ("running", "treadmill", "track_run", "trail_run", "ultra_run")),
    ("ride", ("cycling", "biking", "bike", "ride", "spinning", "gravel", "mtb")),
    ("swim", ("swim",)),
    ("walk", ("walking", "hiking", "hike", "walk")),
    ("strength", ("strength", "hiit", "cardio", "fitness_equipment", "indoor_rowing", "yoga",
                  "pilates", "elliptical", "stair")),
)


def classify_sport(type_key: str | None) -> str:
    key = (type_key or "").lower()
    for sport, needles in _SPORT_KEYWORDS:
        if any(needle in key for needle in needles):
            return sport
    return "other"


def parse_activities(payload: Any) -> list[Row]:
    rows = []
    for item in payload or []:
        activity_id = _get(item, "activityId")
        start_local = parse_timestamp(_get(item, "startTimeLocal"))
        if activity_id is None or start_local is None:
            continue
        type_key = _get(item, "activityType", "typeKey")
        zones = [_num(_get(item, f"hrTimeInZone_{n}")) for n in range(1, 6)]
        cadence = _get(item, "averageRunningCadenceInStepsPerMinute")
        if cadence is None:
            cadence = _get(item, "averageBikingCadenceInRevPerMinute")
        rows.append(
            {
                "activity_id": int(activity_id),
                "date": start_local.date(),
                "name": _get(item, "activityName"),
                "type_key": type_key,
                "sport": classify_sport(type_key),
                "start_local": start_local,
                "duration_s": _num(_get(item, "duration")),
                "moving_s": _num(_get(item, "movingDuration")),
                "distance_m": _num(_get(item, "distance")),
                "elevation_gain_m": _num(_get(item, "elevationGain")),
                "avg_speed_mps": _num(_get(item, "averageSpeed")),
                "max_speed_mps": _num(_get(item, "maxSpeed")),
                "avg_hr": _num(_get(item, "averageHR"), allow_zero=False),
                "max_hr": _num(_get(item, "maxHR"), allow_zero=False),
                "calories": _num(_get(item, "calories")),
                "aerobic_te": _num(_get(item, "aerobicTrainingEffect")),
                "anaerobic_te": _num(_get(item, "anaerobicTrainingEffect")),
                "training_load": _num(_get(item, "activityTrainingLoad")),
                "vo2max": _num(_get(item, "vO2MaxValue"), allow_zero=False),
                "hr_zone_s": zones if any(z for z in zones) else None,
                "avg_power": _num(_get(item, "avgPower"), allow_zero=False),
                "norm_power": _num(_get(item, "normPower"), allow_zero=False),
                "avg_cadence": _num(cadence, allow_zero=False),
                "steps": _int(_get(item, "steps")),
                "start_lat": _get(item, "startLatitude"),
                "start_lon": _get(item, "startLongitude"),
                "has_polyline": bool(_get(item, "hasPolyline")),
                "is_pr": bool(_get(item, "isPR")),
            }
        )
    return rows


# --- intraday series (day view) ------------------------------------------------------------


def parse_heart_rate_series(payload: Any) -> list[list[float]]:
    """``[[epoch_ms, bpm], ...]`` from the dailyHeartRate endpoint."""
    descriptors = _get(payload, "heartRateValueDescriptors") or []
    index = {d.get("key"): d.get("index") for d in descriptors if isinstance(d, dict)}
    ts_i, hr_i = index.get("timestamp", 0), index.get("heartrate", 1)
    series = []
    for row in _get(payload, "heartRateValues") or []:
        if not isinstance(row, list) or len(row) <= max(ts_i, hr_i):
            continue
        if row[ts_i] is not None and row[hr_i] is not None:
            series.append([row[ts_i], row[hr_i]])
    return series


def parse_body_battery_series(payload: Any) -> list[list[float]]:
    """``[[epoch_ms, level], ...]`` from a single-day Body Battery report."""
    report = payload[0] if isinstance(payload, list) and payload else payload
    descriptors = _get(report, "bodyBatteryValueDescriptorDTOList") or []
    index = {
        d.get("bodyBatteryValueDescriptorKey"): d.get("bodyBatteryValueDescriptorIndex")
        for d in descriptors
        if isinstance(d, dict)
    }
    ts_i, level_i = index.get("timestamp", 0), index.get("bodyBatteryLevel", 1)
    series = []
    for row in _get(report, "bodyBatteryValuesArray") or []:
        if not isinstance(row, list) or len(row) <= max(ts_i, level_i):
            continue
        if row[ts_i] is not None and row[level_i] is not None:
            series.append([row[ts_i], row[level_i]])
    return series
