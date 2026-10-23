import datetime as dt
import random

import pytest

from garmin_dashboard.db import session_scope
from garmin_dashboard.demo import seed_demo
from garmin_dashboard.garmin.sync import upsert_rows
from garmin_dashboard.insights import cohens_d, find_insights, pearson, weekly_digest
from garmin_dashboard.models import Activity, DailySummary, Goal, Person, Sleep, SyncState

END = dt.date(2026, 10, 22)
ALL = {"sleep", "activity", "workouts", "body"}


def test_effect_size_helpers():
    assert cohens_d([1, 2, 3], [1, 2, 3]) == 0
    assert cohens_d([5, 6, 7], [1, 2, 3]) == pytest.approx(4.0)
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None  # no variance


@pytest.fixture
def person_id(settings):
    with session_scope() as db:
        person = Person(name="P")
        db.add(person)
        db.flush()
        return person.id


def _seed(person_id: int, *, workout_boost: float, seed: int) -> None:
    """90 days: workouts on alternate days; optionally better sleep the night after."""
    rng = random.Random(seed)
    start = END - dt.timedelta(days=89)
    sleeps, activities = [], []
    for i in range(90):
        day = start + dt.timedelta(days=i)
        worked = i % 2 == 0
        if worked:
            activities.append({"activity_id": 1000 + i, "date": day, "sport": "run",
                               "duration_s": 3600, "training_load": 120})
        after_workout = (i - 1) % 2 == 0 and i > 0
        score = 70 + (workout_boost if after_workout else 0) + rng.gauss(0, 4)
        sleeps.append({"date": day, "score": round(score), "duration_s": 26000,
                       "deep_s": 5000})
    with session_scope() as db:
        upsert_rows(db, Sleep, person_id, sleeps)
        upsert_rows(db, Activity, person_id, activities)
        db.add(SyncState(person_id=person_id, dataset="activities", synced_from=start,
                         synced_through=END))


def test_workout_sleep_pattern_is_found(person_id):
    _seed(person_id, workout_boost=8, seed=1)
    with session_scope() as db:
        found = {i["id"]: i for i in find_insights(db, person_id, END, 90, ALL)}
    insight = found["workout_sleep"]
    after, rest = insight["groups"]
    assert after["mean"] > rest["mean"] + 5
    assert insight["favourable"] is True and insight["strength"] in ("moderate", "strong")


def test_noise_produces_no_workout_insight(person_id):
    _seed(person_id, workout_boost=0, seed=2)
    with session_scope() as db:
        ids = {i["id"] for i in find_insights(db, person_id, END, 90, ALL)}
    assert "workout_sleep" not in ids


def test_insights_respect_categories(person_id):
    _seed(person_id, workout_boost=8, seed=1)
    with session_scope() as db:
        assert find_insights(db, person_id, END, 90, {"workouts"}) == []


def test_weekly_digest(person_id):
    week = dt.date(2026, 10, 12)  # Monday
    with session_scope() as db:
        rows = [{"date": week - dt.timedelta(days=i), "steps": 8000} for i in range(1, 29)]
        rows += [{"date": week + dt.timedelta(days=i), "steps": 10000 + i * 1000}
                 for i in range(7)]
        upsert_rows(db, DailySummary, person_id, rows)
        db.add(Goal(person_id=person_id, metric_key="steps", comparison="at_least",
                    target=12000, period="day"))
        db.flush()
        digest = weekly_digest(db, person_id, week + dt.timedelta(days=3), "monday", ALL)
    assert digest["week"] == "2026-10-12"
    steps = digest["metrics"]["steps"]
    assert steps["value"] == sum(10000 + i * 1000 for i in range(7))
    assert steps["usual"] == 56000 and steps["delta_pct"] == pytest.approx(62.5)
    most_active = next(h for h in digest["highlights"] if h["kind"] == "most_active_day")
    assert most_active["date"] == "2026-10-18" and most_active["value"] == 16000
    assert digest["goals"][0]["met_days"] == 5  # 12k..16k
    assert digest["notable"][0] == {"metric": "steps", "delta_pct": 62.5, "good": True}


def test_digest_and_insights_endpoints(client, admin):
    ids = seed_demo()
    params = {"people": ",".join(map(str, ids))}
    digest = client.get("/api/digest", params=params).json()
    alex = digest["people"][str(ids[0])]
    assert alex["has_data"] and alex["metrics"]["sleep_score"]["value"] is not None
    insights = client.get("/api/insights", params=params).json()
    assert set(insights["people"]) == {str(i) for i in ids}


def test_verify_report_on_demo_data(settings):
    from garmin_dashboard.verify import report

    ids = seed_demo()
    with session_scope() as db:
        result = report(db, ids[0])
    tables = result["tables"]
    assert tables["daily_summaries"]["rows"] == 240
    assert tables["sleep"]["checks"]["implausible_sleep_windows"]["count"] == 0
    assert result["raw"]["raw_weight_values"]["looks_like"] == "grams"
    assert result["raw"]["sleep_fields"]["int"] == 240  # epoch-millis timestamps
