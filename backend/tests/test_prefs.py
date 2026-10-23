import datetime as dt

import pytest
from sqlalchemy import create_engine, inspect, text

from garmin_dashboard import prefs
from garmin_dashboard.analytics import bucket_start
from garmin_dashboard.db import init_engine


def test_garmin_profile_maps_to_preferences():
    profile = {
        "measurementSystem": "statute_us",
        "firstDayOfWeek": {"dayId": 1, "dayName": "sunday"},
        "timeFormat": {"formatKey": "time_twelve_hr"},
    }
    assert prefs.from_garmin_profile(profile) == {
        "distance": "mi", "weight": "lb", "volume": "floz", "elevation": "ft",
        "week_start": "sunday", "time_format": "12h",
    }
    assert prefs.from_garmin_profile(None) == {}


def test_own_choices_beat_garmin_which_beats_defaults():
    result = prefs.effective({"weight": "st"}, {"weight": "lb", "distance": "mi"})
    assert result["weight"] == "st" and result["distance"] == "mi" and result["volume"] == "ml"


def test_validate_rejects_unknown_values():
    with pytest.raises(ValueError):
        prefs.validate({"distance": "furlongs"})
    with pytest.raises(ValueError):
        prefs.validate({"colour": "blue"})


def test_week_buckets_follow_week_start():
    wednesday = dt.date(2026, 10, 21)
    assert bucket_start(wednesday, "week") == dt.date(2026, 10, 19)  # Monday
    assert bucket_start(wednesday, "week", "sunday") == dt.date(2026, 10, 18)
    sunday = dt.date(2026, 10, 25)
    assert bucket_start(sunday, "week", "sunday") == sunday


def test_preferences_api_merges_and_resets(client, admin):
    url = f"/api/people/{admin['id']}"
    body = client.patch(url, json={"preferences": {"distance": "mi", "weight": "st"}}).json()
    assert body["preferences"]["distance"] == "mi" and body["preferences"]["weight"] == "st"
    body = client.patch(url, json={"preferences": {"weight": None}}).json()
    assert body["preference_overrides"] == {"distance": "mi"}
    assert body["preferences"]["weight"] == "kg"
    assert client.patch(url, json={"preferences": {"distance": "leagues"}}).status_code == 422


def test_new_nullable_columns_are_added_to_old_databases(tmp_path):
    url = f"sqlite:///{(tmp_path / 'old.sqlite3').as_posix()}"
    old = create_engine(url)
    with old.begin() as conn:  # a 'people' table from before preferences existed
        conn.execute(text(
            "CREATE TABLE people (id INTEGER PRIMARY KEY, name VARCHAR(80), color_slot INTEGER, "
            "username VARCHAR(80), password_hash VARCHAR(255), is_admin BOOLEAN, is_demo BOOLEAN, "
            "shared_categories JSON, history_start DATE, created_at DATETIME)"
        ))
    old.dispose()
    engine = init_engine(url)
    columns = {c["name"] for c in inspect(engine).get_columns("people")}
    assert {"preferences", "garmin_preferences"} <= columns
