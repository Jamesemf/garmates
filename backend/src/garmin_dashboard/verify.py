"""Data-quality report for synced Garmin data (``garmin-dashboard verify``).

Checks what the parsers produced from real API responses: coverage, missing values,
values outside plausible human ranges, and the raw formats Garmin actually sent (e.g.
weight in grams vs kilograms, timestamps as epoch millis vs ISO strings). Reads only the
local database.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analytics import clock_hours
from .models import Activity, DailySummary, Hrv, Person, RawPayload, Sleep, SyncRun, Weight

# (column, low, high) - values outside are flagged, not dropped.
RANGES: dict[type, list[tuple[str, float, float]]] = {
    DailySummary: [
        ("steps", 0, 100_000), ("rhr", 25, 110), ("stress_avg", 0, 100), ("bb_max", 5, 100),
        ("bb_min", 0, 100), ("calories_total", 800, 9000), ("spo2_avg", 70, 100),
        ("resp_avg", 5, 40), ("intensity_moderate", 0, 1000), ("floors_up", 0, 500),
    ],
    Sleep: [
        ("duration_s", 3600, 16 * 3600), ("score", 0, 100), ("deep_s", 0, 6 * 3600),
        ("rem_s", 0, 6 * 3600), ("avg_hr", 25, 120), ("avg_resp", 5, 30),
    ],
    Hrv: [("last_night_avg", 5, 250), ("weekly_avg", 5, 250)],
    Weight: [("weight_kg", 25, 250), ("body_fat_pct", 2, 70), ("bmi", 10, 70)],
    Activity: [
        ("duration_s", 60, 24 * 3600), ("distance_m", 0, 400_000), ("avg_hr", 40, 220),
        ("avg_speed_mps", 0, 40), ("vo2max", 15, 95), ("training_load", 0, 2000),
    ],
}
KEY_COLUMNS: dict[type, list[str]] = {
    DailySummary: ["steps", "rhr", "stress_avg", "bb_max", "calories_total", "intensity_moderate",
                   "spo2_avg", "resp_avg", "hydration_ml"],
    Sleep: ["score", "duration_s", "deep_s", "rem_s", "start_local", "end_local", "avg_hr"],
    Hrv: ["last_night_avg", "weekly_avg", "status"],
    Weight: ["weight_kg", "body_fat_pct"],
    Activity: ["distance_m", "avg_hr", "training_load", "vo2max", "hr_zone_s", "type_key"],
}


def _table_report(db: Session, model: type, person_id: int) -> dict[str, Any]:
    rows = db.scalars(select(model).where(model.person_id == person_id)).all()
    if not rows:
        return {"rows": 0}
    dates = [r.date for r in rows]
    report: dict[str, Any] = {
        "rows": len(rows),
        "from": min(dates).isoformat(),
        "to": max(dates).isoformat(),
        "missing_pct": {},
        "out_of_range": {},
    }
    for column in KEY_COLUMNS.get(model, []):
        missing = sum(1 for r in rows if getattr(r, column) is None)
        report["missing_pct"][column] = round(missing / len(rows) * 100)
    for column, low, high in RANGES.get(model, []):
        bad = [
            (r.date.isoformat(), getattr(r, column))
            for r in rows
            if getattr(r, column) is not None and not low <= getattr(r, column) <= high
        ]
        if bad:
            report["out_of_range"][column] = {"count": len(bad), "examples": bad[:3],
                                              "expected": [low, high]}
    if model is Sleep:
        report["checks"] = _sleep_checks(rows)
    if model is Activity:
        report["sports"] = dict(Counter(r.sport for r in rows).most_common())
        unknown = Counter(r.type_key for r in rows if r.sport == "other")
        if unknown:
            report["unclassified_types"] = dict(unknown.most_common(8))
    return report


def _sleep_checks(rows: list[Sleep]) -> dict[str, Any]:
    stage_mismatch = []
    odd_bedtimes = []
    for r in rows:
        stages = [r.deep_s, r.light_s, r.rem_s]
        if r.duration_s and all(s is not None for s in stages):
            total = sum(stages)
            if abs(total - r.duration_s) > 0.2 * r.duration_s:
                stage_mismatch.append((r.date.isoformat(), r.duration_s, total))
        if r.start_local and r.end_local:
            bed = clock_hours(r.start_local, r.date - dt.timedelta(days=1))
            if not 16 <= bed <= 34 or r.end_local <= r.start_local:
                odd_bedtimes.append((r.date.isoformat(), r.start_local.isoformat(),
                                     r.end_local.isoformat()))
    return {
        "stages_not_matching_duration": {"count": len(stage_mismatch),
                                         "examples": stage_mismatch[:3]},
        "implausible_sleep_windows": {"count": len(odd_bedtimes), "examples": odd_bedtimes[:3]},
    }


def _raw_formats(db: Session, person_id: int) -> dict[str, Any]:
    """Which shapes/units Garmin really sent - the parser assumptions to confirm."""
    formats: dict[str, Any] = {}
    payloads = db.scalars(select(RawPayload).where(RawPayload.person_id == person_id)).all()
    by_dataset: dict[str, list[Any]] = {}
    for raw in payloads:
        by_dataset.setdefault(raw.dataset, []).append(json.loads(raw.payload))
    formats["datasets"] = {k: len(v) for k, v in sorted(by_dataset.items())}

    sleep_types: Counter[str] = Counter()
    for payload in by_dataset.get("sleep", []):
        for item in payload if isinstance(payload, list) else []:
            value = item.get("sleepStartTimestampLocal") if isinstance(item, dict) else None
            if value is not None:
                sleep_types[type(value).__name__] += 1
            scores = item.get("sleepScores") if isinstance(item, dict) else None
            if isinstance(scores, dict):
                for key in scores:
                    sleep_types[f"score:{key}"] += 1
    formats["sleep_fields"] = dict(sleep_types.most_common(12))

    weights = []
    for payload in by_dataset.get("weight", []):
        for summary in (payload or {}).get("dailyWeightSummaries") or []:
            latest = summary.get("latestWeight") or {}
            if isinstance(latest.get("weight"), int | float):
                weights.append(latest["weight"])
    if weights:
        formats["raw_weight_values"] = {
            "min": min(weights), "max": max(weights),
            "looks_like": "grams" if min(weights) > 500 else "kilograms",
        }

    activity_keys: Counter[str] = Counter()
    for payload in by_dataset.get("activities", []):
        for item in payload if isinstance(payload, list) else []:
            if isinstance(item, dict):
                activity_keys[str((item.get("activityType") or {}).get("typeKey"))] += 1
    formats["activity_type_keys"] = dict(activity_keys.most_common(10))
    return formats


def report(db: Session, person_id: int) -> dict[str, Any]:
    person = db.get(Person, person_id)
    last_run = db.scalar(
        select(SyncRun).where(SyncRun.person_id == person_id).order_by(SyncRun.id.desc()).limit(1)
    )
    return {
        "person": person.name if person else person_id,
        "last_sync": None if last_run is None else {
            "status": last_run.status, "finished": str(last_run.finished_at),
            "message": last_run.message,
        },
        "tables": {
            model.__tablename__: _table_report(db, model, person_id)
            for model in (DailySummary, Sleep, Hrv, Weight, Activity)
        },
        "raw": _raw_formats(db, person_id),
    }


def people_with_data(db: Session) -> list[int]:
    return list(db.scalars(select(RawPayload.person_id).group_by(RawPayload.person_id)
                           .having(func.count() > 0)))
