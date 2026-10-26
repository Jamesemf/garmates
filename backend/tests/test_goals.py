import datetime as dt

import pytest

from garmates.analytics import clock_hours, load_daily
from garmates.db import session_scope
from garmates.garmin.sync import upsert_rows
from garmates.goals import challenge_board, evaluate_goal, period_bounds
from garmates.models import Challenge, DailySummary, Goal, Person, Sleep

TODAY = dt.date(2026, 10, 22)  # a Thursday


@pytest.fixture
def two_people(settings):
    with session_scope() as db:
        a, b = Person(name="A"), Person(name="B")
        db.add_all([a, b])
        db.flush()
        return a.id, b.id


def _steps(person_id: int, values: dict[dt.date, int]) -> None:
    with session_scope() as db:
        rows = [{"date": d, "steps": v} for d, v in values.items()]
        upsert_rows(db, DailySummary, person_id, rows)


def test_period_bounds():
    assert period_bounds(TODAY, "week", "monday") == (dt.date(2026, 10, 19), dt.date(2026, 10, 25))
    assert period_bounds(TODAY, "week", "sunday") == (dt.date(2026, 10, 18), dt.date(2026, 10, 24))
    assert period_bounds(TODAY, "month", "monday") == (dt.date(2026, 10, 1), dt.date(2026, 10, 31))


def test_daily_goal_history_and_streak(two_people):
    pid, _ = two_people
    # 12k for the last 4 days before today, 5k before that, nothing yet today
    _steps(pid, {TODAY - dt.timedelta(days=i): 12_000 if i <= 4 else 5_000 for i in range(1, 10)})
    with session_scope() as db:
        goal = Goal(person_id=pid, metric_key="steps", comparison="at_least", target=10_000,
                    period="day")
        result = evaluate_goal(db, goal, TODAY, "monday")
    assert result["current"]["status"] == "no_data"
    assert result["streak"] == 4
    assert [h["met"] for h in result["history"][-5:]] == [False, True, True, True, True]


def test_weekly_total_goal_tracks_pace(two_people):
    pid, _ = two_people
    monday = dt.date(2026, 10, 19)
    _steps(pid, {monday + dt.timedelta(days=i): 9_000 for i in range(4)})  # Mon-Thu
    with session_scope() as db:
        on_pace = Goal(person_id=pid, metric_key="steps", target=60_000, period="week")
        behind = Goal(person_id=pid, metric_key="steps", target=80_000, period="week")
        capped = Goal(person_id=pid, metric_key="steps", comparison="at_most", target=30_000,
                      period="week")
        current = evaluate_goal(db, on_pace, TODAY, "monday")["current"]
        assert current["value"] == 36_000 and current["elapsed_days"] == 4
        assert current["status"] == "on_track"  # 36k >= 60k * 4/7
        assert evaluate_goal(db, behind, TODAY, "monday")["current"]["status"] == "behind"
        assert evaluate_goal(db, capped, TODAY, "monday")["current"]["status"] == "missed"


def test_bedtime_averages_across_midnight(two_people):
    pid, _ = two_people
    night = dt.date(2026, 10, 21)
    with session_scope() as db:
        upsert_rows(db, Sleep, pid, [
            {"date": night, "start_local": dt.datetime(2026, 10, 20, 23, 30),
             "end_local": dt.datetime(2026, 10, 21, 6, 45), "duration_s": 25000},
            {"date": TODAY, "start_local": dt.datetime(2026, 10, 22, 0, 30),
             "end_local": dt.datetime(2026, 10, 22, 7, 15), "duration_s": 24000},
        ])
        series = load_daily(db, pid, ["bedtime", "wake_time"], night, TODAY)
    assert series[night]["bedtime"] == 23.5 and series[TODAY]["bedtime"] == 24.5
    assert series[night]["wake_time"] == 6.75
    assert clock_hours(dt.datetime(2026, 10, 22, 0, 30), dt.date(2026, 10, 21)) == 24.5


def test_challenge_board_ranks_totals_and_improvement(two_people):
    a, b = two_people
    start = TODAY - dt.timedelta(days=2)
    # A: usual 5k -> 8k in challenge (+60%); B: usual 10k -> 11k (+10%) but higher total
    _steps(a, {start - dt.timedelta(days=i): 5_000 for i in range(1, 11)})
    _steps(a, {start + dt.timedelta(days=i): 8_000 for i in range(3)})
    _steps(b, {start - dt.timedelta(days=i): 10_000 for i in range(1, 11)})
    _steps(b, {start + dt.timedelta(days=i): 11_000 for i in range(3)})
    with session_scope() as db:
        total = Challenge(name="Steps", metric_key="steps", scoring="total", start_date=start,
                          end_date=start + dt.timedelta(days=6), participant_ids=[a, b])
        board = challenge_board(db, total, {a, b}, TODAY)
        assert board["status"] == "active"
        assert [e["person_id"] for e in board["entries"]] == [b, a]
        assert board["entries"][0]["score"] == 33_000
        assert board["race"][-1] == {"date": TODAY.isoformat(), f"p{a}": 24_000, f"p{b}": 33_000}

        total.scoring = "improvement"
        board = challenge_board(db, total, {a, b}, TODAY)
        assert [e["person_id"] for e in board["entries"]] == [a, b]
        assert board["entries"][0]["score"] == 60.0

        hidden = challenge_board(db, total, {a}, TODAY)
        assert next(e for e in hidden["entries"] if e["person_id"] == b)["hidden"] is True


def test_goal_and_challenge_api_rules(client, admin):
    partner = client.post(
        "/api/people", json={"name": "Partner", "username": "partner", "password": "partner-pw"}
    ).json()

    mine = client.post("/api/goals", json={"person_id": admin["id"], "metric_key": "steps",
                                           "target": 10000, "period": "day"})
    assert mine.status_code == 201 and mine.json()["current"]["status"] == "no_data"
    theirs = client.post("/api/goals", json={"person_id": partner["id"], "metric_key": "steps",
                                             "target": 10000})
    assert theirs.status_code == 403
    assert len(client.get("/api/goals", params={"people": admin["id"]}).json()["goals"]) == 1

    today = dt.date.today().isoformat()
    body = {"name": "Step-off", "metric_key": "steps", "scoring": "total", "start_date": today,
            "end_date": today, "participant_ids": [admin["id"], partner["id"]]}
    created = client.post("/api/challenges", json=body)
    assert created.status_code == 201, created.text
    assert len(client.get("/api/challenges").json()["challenges"]) == 1

    no_direction = client.post("/api/challenges", json={**body, "metric_key": "weight",
                                                        "scoring": "average"})
    assert no_direction.status_code == 422
    not_total = client.post("/api/challenges", json={**body, "metric_key": "hrv"})
    assert not_total.status_code == 422

    # Partner stops sharing daily activity: can't be challenged on steps any more.
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "partner", "password": "partner-pw"})
    client.patch(f"/api/people/{partner['id']}", json={"shared_categories": ["sleep"]})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "james", "password": "correct-horse"})
    assert client.post("/api/challenges", json=body).status_code == 403
