import datetime as dt

import pytest

from garmin_dashboard.api import people as people_api
from garmin_dashboard.demo import seed_demo


def test_setup_once_then_login(client, admin):
    assert admin["is_admin"] and admin["is_me"]
    again = client.post("/api/auth/setup",
                        json={"name": "X", "username": "someone", "password": "password1"})
    assert again.status_code == 409

    client.post("/api/auth/logout")
    assert client.get("/api/people").status_code == 401
    bad = client.post("/api/auth/login", json={"username": "james", "password": "nope"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"username": "James", "password": "correct-horse"})
    assert good.status_code == 200
    assert client.get("/api/auth/state").json()["me"]["name"] == "James"


def test_state_changing_requests_need_csrf_header(client, admin):
    response = client.post("/api/people", json={"name": "Partner"}, headers={"X-GD-Request": ""})
    assert response.status_code == 403


def test_sharing_controls_what_others_see(client, admin):
    partner = client.post(
        "/api/people", json={"name": "Partner", "username": "partner", "password": "partner-pw"}
    ).json()
    assert partner["color_slot"] != admin["color_slot"]

    # Admin can't change settings for someone who has their own login.
    denied = client.patch(f"/api/people/{partner['id']}", json={"shared_categories": []})
    assert denied.status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "partner", "password": "partner-pw"})
    client.patch(f"/api/people/{partner['id']}", json={"shared_categories": ["workouts"]})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "james", "password": "correct-horse"})

    series = client.get(
        "/api/series", params={"people": partner["id"], "metrics": "sleep_score,workouts"}
    ).json()
    assert series["people"][str(partner["id"])]["hidden"] == ["sleep_score"]


@pytest.fixture
def demo(client, admin):
    return seed_demo(today=dt.date.today())


def test_demo_data_flows_through_every_endpoint(client, demo):
    ids = ",".join(map(str, demo))
    people = client.get("/api/people").json()
    assert {p["name"] for p in people} >= {"Alex (demo)", "Sam (demo)"}

    series = client.get("/api/series", params={
        "people": ids, "metrics": "sleep_score,hrv,steps,workouts,weight", "bucket": "week",
    }).json()
    alex = series["people"][str(demo[0])]["points"]
    assert alex and alex[-1]["sleep_score"] is not None

    summary = client.get("/api/summary", params={"people": ids, "metrics": "rhr,hrv,steps"}).json()
    rhr = summary["people"][str(demo[0])]["metrics"]["rhr"]
    assert rhr["value"] is not None and rhr["baseline"] is not None and rhr["n"] == 7

    stats = client.get("/api/workouts/stats", params={"people": ids}).json()
    assert stats["people"][str(demo[0])]["by_sport"]["run"]["count"] > 0
    assert stats["people"][str(demo[0])]["load"]

    activities = client.get("/api/activities", params={"people": ids}).json()["activities"]
    with_track = next(a for a in activities if a["has_polyline"])
    detail = client.get(f"/api/activities/{with_track['activity_id']}").json()
    assert len(detail["track"]["points"]) > 100

    day = client.get("/api/day", params={"people": ids,
                                        "date": (dt.date.today() - dt.timedelta(days=2))}).json()
    assert day["people"][str(demo[0])]["heart_rate"]


def test_adding_a_key_validates_and_starts_sync(client, admin, monkeypatch):
    class FakeConnector:
        def __init__(self, api_key, *_, **__):
            if api_key == "rejected-key":
                raise people_api.KeyRejectedError("Garmin rejected this key")
            self.client = type("C", (), {"get_user_profile_settings": lambda self: {
                "displayName": "james-garmin"}})()

        def call(self, method, *args):
            return method(*args)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    submitted = []
    monkeypatch.setattr(people_api, "GarminConnector", FakeConnector)
    monkeypatch.setattr(people_api.sync_manager, "submit", submitted.append)

    bad = client.put(f"/api/people/{admin['id']}/garmin-key", json={"api_key": "rejected-key"})
    assert bad.status_code == 400

    ok = client.put(f"/api/people/{admin['id']}/garmin-key",
                    json={"api_key": "a-very-real-key-1234", "expires_on": "2027-10-23"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["key"]["hint"] == "…1234"
    assert body["key"]["garmin_display_name"] == "james-garmin"
    assert submitted == [admin["id"]]
    assert "a-very-real-key-1234" not in str(client.get("/api/people").json())


def test_people_without_synced_data_get_no_zero_filled_workouts(client, admin):
    series = client.get(
        "/api/series", params={"people": admin["id"], "metrics": "workouts,workout_hours"}
    ).json()
    assert series["people"][str(admin["id"])]["points"] == []


def test_security_headers(client):
    response = client.get("/api/auth/state")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
