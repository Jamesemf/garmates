"""Read-only data endpoints behind the charts. Every response respects sharing settings."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from .. import analytics
from ..catalog import METRICS_BY_KEY, catalog_payload
from ..garmin.detail import get_activity_track, get_day_detail
from ..models import Activity, DailySummary, Hrv, Person, Sleep
from .deps import DB, Me, PeopleParam, date_range, get_person_or_404, visible_categories

router = APIRouter(prefix="/api", tags=["data"])

Bucket = Literal["day", "week", "month"]
WeekStart = Literal["monday", "sunday"]


def _metric_list(metrics: str) -> list[str]:
    keys = [m.strip() for m in metrics.split(",") if m.strip()]
    unknown = [k for k in keys if k not in METRICS_BY_KEY]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown metrics: {unknown}")
    return keys


def _allowed(viewer: Person, person: Person, keys: list[str]) -> tuple[list[str], list[str]]:
    categories = set(visible_categories(viewer, person))
    allowed = [k for k in keys if METRICS_BY_KEY[k].category in categories]
    hidden = [k for k in keys if k not in allowed]
    return allowed, hidden


@router.get("/catalog")
def catalog(_: Me) -> dict:
    return catalog_payload()


@router.get("/series")
def series(
    me: Me,
    db: DB,
    people: PeopleParam,
    metrics: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    bucket: Bucket = "day",
    week_start: WeekStart = "monday",
) -> dict:
    """Per-person time series for the requested metrics."""
    start, end = date_range(start, end)
    keys = _metric_list(metrics)
    out = {}
    for person in people:
        allowed, hidden = _allowed(me, person, keys)
        data = analytics.load_daily(db, person.id, allowed, start, end)
        out[str(person.id)] = {
            "points": analytics.rollup(data, allowed, bucket, week_start),
            "hidden": hidden,
        }
    return {"start": start.isoformat(), "end": end.isoformat(), "bucket": bucket, "people": out}


@router.get("/summary")
def summary(
    me: Me,
    db: DB,
    people: PeopleParam,
    metrics: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    baseline_days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> dict:
    """Period averages compared with each person's own preceding baseline."""
    start, end = date_range(start, end, default_days=7)
    keys = _metric_list(metrics)
    out = {}
    for person in people:
        allowed, hidden = _allowed(me, person, keys)
        out[str(person.id)] = {
            "metrics": analytics.summarise(db, person.id, allowed, start, end, baseline_days),
            "hidden": hidden,
        }
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "baseline_days": baseline_days,
        "people": out,
    }


@router.get("/day")
def day_view(me: Me, db: DB, people: PeopleParam, date: dt.date | None = None) -> dict:
    """One day side by side: summary numbers plus intraday heart rate and Body Battery."""
    day = date or dt.date.today()
    out = {}
    for person in people:
        categories = set(visible_categories(me, person))
        entry: dict = {"hidden": [c for c in ("sleep", "activity") if c not in categories]}
        if "sleep" in categories:
            sleep = db.get(Sleep, (person.id, day))
            hrv = db.get(Hrv, (person.id, day))
            entry["sleep"] = None if sleep is None else {
                "score": sleep.score,
                "duration_s": sleep.duration_s,
                "deep_s": sleep.deep_s,
                "light_s": sleep.light_s,
                "rem_s": sleep.rem_s,
                "awake_s": sleep.awake_s,
                "start_local": sleep.start_local.isoformat() if sleep.start_local else None,
                "end_local": sleep.end_local.isoformat() if sleep.end_local else None,
                "avg_hr": sleep.avg_hr,
                "feedback": sleep.feedback,
            }
            entry["hrv"] = None if hrv is None else {
                "last_night_avg": hrv.last_night_avg,
                "weekly_avg": hrv.weekly_avg,
                "status": hrv.status,
            }
        daily = db.get(DailySummary, (person.id, day))
        if daily is not None:
            entry["daily"] = {
                "steps": daily.steps if "activity" in categories else None,
                "step_goal": daily.step_goal if "activity" in categories else None,
                "rhr": daily.rhr if "sleep" in categories else None,
                "stress_avg": daily.stress_avg if "sleep" in categories else None,
                "bb_max": daily.bb_max if "sleep" in categories else None,
                "bb_min": daily.bb_min if "sleep" in categories else None,
            }
        if "sleep" in categories:
            # Intraday HR/Body Battery are recovery data; fetch live only for real profiles.
            detail = get_day_detail(person.id, day, allow_fetch=person.credential is not None)
            entry["heart_rate"] = detail["heart_rate"]
            entry["body_battery"] = detail["body_battery"]
            entry["detail_error"] = detail["error"]
        out[str(person.id)] = entry
    return {"date": day.isoformat(), "people": out}


def _activity_out(act: Activity) -> dict:
    return {
        "activity_id": act.activity_id,
        "person_id": act.person_id,
        "date": act.date.isoformat(),
        "name": act.name,
        "type_key": act.type_key,
        "sport": act.sport,
        "start_local": act.start_local.isoformat() if act.start_local else None,
        "duration_s": act.duration_s,
        "moving_s": act.moving_s,
        "distance_m": act.distance_m,
        "elevation_gain_m": act.elevation_gain_m,
        "avg_speed_mps": act.avg_speed_mps,
        "max_speed_mps": act.max_speed_mps,
        "avg_hr": act.avg_hr,
        "max_hr": act.max_hr,
        "calories": act.calories,
        "aerobic_te": act.aerobic_te,
        "anaerobic_te": act.anaerobic_te,
        "training_load": act.training_load,
        "vo2max": act.vo2max,
        "hr_zone_s": act.hr_zone_s,
        "avg_power": act.avg_power,
        "avg_cadence": act.avg_cadence,
        "has_polyline": act.has_polyline,
        "is_pr": act.is_pr,
    }


@router.get("/activities")
def list_activities(
    me: Me,
    db: DB,
    people: PeopleParam,
    start: dt.date | None = None,
    end: dt.date | None = None,
    sport: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    start, end = date_range(start, end, default_days=90)
    ids = [p.id for p in people if "workouts" in visible_categories(me, p)]
    query = (
        select(Activity)
        .where(Activity.person_id.in_(ids), Activity.date >= start, Activity.date <= end)
        .order_by(Activity.start_local.desc())
        .limit(limit)
    )
    if sport:
        query = query.where(Activity.sport == sport)
    return {"activities": [_activity_out(a) for a in db.scalars(query)]}


@router.get("/activities/{activity_id}")
def activity_detail(activity_id: int, me: Me, db: DB) -> dict:
    act = db.get(Activity, activity_id)
    if act is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such activity")
    owner = get_person_or_404(db, act.person_id)
    if "workouts" not in visible_categories(me, owner):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not shared with you")
    out = _activity_out(act)
    db.close()  # don't hold a connection while the FIT file downloads
    out["track"] = get_activity_track(activity_id)
    return out


@router.get("/workouts/stats")
def workouts_stats(
    me: Me,
    db: DB,
    people: PeopleParam,
    start: dt.date | None = None,
    end: dt.date | None = None,
    bucket: Bucket = "week",
    week_start: WeekStart = "monday",
) -> dict:
    start, end = date_range(start, end, default_days=90)
    out = {}
    for person in people:
        if "workouts" not in visible_categories(me, person):
            out[str(person.id)] = {"hidden": True}
            continue
        out[str(person.id)] = analytics.workout_stats(
            db, person.id, start, end, bucket, week_start
        )
    return {"start": start.isoformat(), "end": end.isoformat(), "bucket": bucket, "people": out}
