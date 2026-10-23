"""Regressions found by the first sync against a real Garmin account."""

import datetime as dt
import json

import pytest
from sqlalchemy import func, select

from garmin_dashboard.analytics import summarise
from garmin_dashboard.db import session_scope
from garmin_dashboard.garmin import parsers
from garmin_dashboard.garmin.sync import (
    DATASETS_BY_NAME,
    RangeDataset,
    reparse_all,
    store_raw,
    sync_dataset,
    upsert_rows,
)
from garmin_dashboard.models import DailySummary, Person, Sleep, SyncState

TODAY = dt.date(2026, 10, 23)


@pytest.fixture
def person_id(settings):
    with session_scope() as db:
        person = Person(name="Real")
        db.add(person)
        db.flush()
        return person.id


def _day(date: dt.date, **extra) -> dict:
    return {
        "calendarDate": date.isoformat(),
        "includesWellnessData": True,
        "wellnessChronology": {"totalDurationInMillis": 24 * 3600 * 1000},
        "movement": {"steps": {"value": 8000}},
        "calories": {"burnedTotal": 2400},
        **extra,
    }


def test_activity_only_days_are_not_daily_summaries():
    payload = {"data": [
        _day(dt.date(2026, 10, 1)),
        # Real example: watch not worn, one activity recorded -> 256 "kcal for the day".
        {"calendarDate": "2026-10-02", "includesWellnessData": False,
         "includesActivityData": True, "calories": {"burnedTotal": 256}},
        _day(dt.date(2026, 10, 3), wellnessChronology={"totalDurationInMillis": 41_400_000}),
    ]}
    rows = {r["date"]: r for r in parsers.parse_daily_summaries(payload)}
    assert set(rows) == {dt.date(2026, 10, 1), dt.date(2026, 10, 3)}
    assert rows[dt.date(2026, 10, 1)]["wear_hours"] == 24.0
    assert rows[dt.date(2026, 10, 3)]["wear_hours"] == 11.5


class StoppedWatch:
    """Garmin has data only up to ``last_upload``; later days come back empty."""

    def __init__(self, last_upload: dt.date):
        self.last_upload = last_upload
        self.calls: list[tuple[dt.date, dt.date]] = []

    def get_daily_summaries(self, start, end):
        self.calls.append((start, end))
        days = (min(end, self.last_upload) - start).days + 1
        return {"data": [_day(start + dt.timedelta(days=i)) for i in range(max(0, days))]}


class Conn:
    def __init__(self, client):
        self.client = client

    def call(self, method, *args, **kwargs):
        return method(*args, **kwargs)


def test_late_uploads_are_fetched_after_the_watch_catches_up(person_id):
    dataset = RangeDataset("daily_summaries", 365, DATASETS_BY_NAME["daily_summaries"].fetch,
                           DATASETS_BY_NAME["daily_summaries"].parse, DailySummary)
    history = TODAY - dt.timedelta(days=60)
    watch = StoppedWatch(last_upload=TODAY - dt.timedelta(days=5))  # e.g. data stops on the 18th
    sync_dataset(Conn(watch), person_id, dataset, history, TODAY)
    with session_scope() as db:
        assert db.get(SyncState, (person_id, "daily_summaries")).synced_through == TODAY

    # The watch syncs again. Before the fix, the catch-up started at TODAY-3 and the
    # rest of the 18th plus the 19th were never fetched.
    watch.last_upload = TODAY
    watch.calls.clear()
    sync_dataset(Conn(watch), person_id, dataset, history, TODAY)
    assert watch.calls[0][0] == TODAY - dt.timedelta(days=5)
    with session_scope() as db:
        days = db.scalar(select(func.count()).select_from(DailySummary))
    assert days == 61


def test_reparse_removes_rows_a_fixed_parser_rejects(person_id):
    payload = {"data": [_day(dt.date(2026, 10, 1)),
                        {"calendarDate": "2026-10-02", "includesWellnessData": False,
                         "calories": {"burnedTotal": 256}}]}
    with session_scope() as db:
        store_raw(db, person_id, "daily_summaries", "2026-10-01..2026-10-02", payload)
        # What the old parser stored: a bogus 256 kcal "day".
        upsert_rows(db, DailySummary, person_id, [{"date": dt.date(2026, 10, 2),
                                                   "calories_total": 256}])
    reparse_all(person_id)
    with session_scope() as db:
        dates = set(db.scalars(select(DailySummary.date)))
    assert dates == {dt.date(2026, 10, 1)}


def test_totals_ignore_unfinished_days_and_bedtime_moves_in_minutes(person_id):
    start = TODAY - dt.timedelta(days=6)
    rows = [{"date": TODAY - dt.timedelta(days=i), "steps": 10_000, "wear_hours": 24.0}
            for i in range(1, 37)]
    rows.append({"date": TODAY, "steps": 1_200, "wear_hours": 9.0})  # this morning so far
    sleeps = [{"date": TODAY - dt.timedelta(days=i), "duration_s": 27000,
               "start_local": dt.datetime.combine(TODAY - dt.timedelta(days=i + 1),
                                                  dt.time(23, 0) if i > 6 else dt.time(23, 30)),
               "end_local": dt.datetime.combine(TODAY - dt.timedelta(days=i), dt.time(7, 0))}
              for i in range(0, 37)]
    with session_scope() as db:
        upsert_rows(db, DailySummary, person_id, rows)
        upsert_rows(db, Sleep, person_id, sleeps)
        result = summarise(db, person_id, ["steps", "bedtime"], start, TODAY, 30)
    # Today's 1,200 steps are left out rather than pulling the week's average down.
    assert result["steps"]["value"] == 10_000 and result["steps"]["n"] == 6
    assert result["bedtime"]["delta_pct"] is None
    assert result["bedtime"]["delta_minutes"] == 30


def test_digest_reports_bedtime_change_in_minutes(person_id):
    from garmin_dashboard.insights import weekly_digest

    week = dt.date(2026, 10, 12)
    sleeps = []
    for i in range(1, 36):
        day = week + dt.timedelta(days=7) - dt.timedelta(days=i)
        late = day >= week
        sleeps.append({"date": day, "duration_s": 27000,
                       "start_local": dt.datetime.combine(day - dt.timedelta(days=1),
                                                          dt.time(23, 45 if late else 15)),
                       "end_local": dt.datetime.combine(day, dt.time(7, 0))})
    with session_scope() as db:
        upsert_rows(db, Sleep, person_id, sleeps)
        digest = weekly_digest(db, person_id, week, "monday", {"sleep"})
    assert digest["metrics"]["bedtime"]["delta_minutes"] == 30
    assert digest["metrics"]["bedtime"]["delta_pct"] is None
    json.dumps(digest)  # serialisable for the API


def test_accidental_short_recordings_are_not_workouts(person_id):
    from garmin_dashboard.analytics import load_daily, workout_stats
    from garmin_dashboard.models import Activity

    day = TODAY - dt.timedelta(days=1)
    with session_scope() as db:
        upsert_rows(db, Activity, person_id, [
            {"activity_id": 1, "date": day, "sport": "run", "duration_s": 1800},
            {"activity_id": 2, "date": day, "sport": "run", "duration_s": 6.0},  # start/stop
        ])
        db.add(SyncState(person_id=person_id, dataset="activities", synced_through=TODAY))
        db.flush()
        assert load_daily(db, person_id, ["workouts"], day, day)[day]["workouts"] == 1
        assert workout_stats(db, person_id, day, day, "week")["by_sport"]["run"]["count"] == 1
