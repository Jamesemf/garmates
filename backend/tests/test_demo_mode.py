"""Public demo mode: synthetic data only, no sign-in, nothing can be changed."""

import pytest
from fastapi.testclient import TestClient

from garmates import config
from garmates.app import create_app
from garmates.db import session_scope
from garmates.models import Person


@pytest.fixture
def demo_app(settings, monkeypatch):
    monkeypatch.setenv("GARMATES_DEMO_MODE", "true")
    config.get_settings.cache_clear()
    return create_app(config.get_settings(), start_scheduler=False)


@pytest.fixture
def demo_client(demo_app):
    with TestClient(demo_app, headers={"X-Garmates-Request": "1"}) as client:
        yield client


def test_visitors_see_the_demo_without_signing_in(demo_client):
    state = demo_client.get("/api/auth/state").json()
    assert state["demo_mode"] is True
    assert state["setup_required"] is False
    assert state["me"]["is_demo"] is True

    people = demo_client.get("/api/people").json()
    assert len(people) == 2 and all(p["is_demo"] for p in people)
    ids = ",".join(str(p["id"]) for p in people)
    series = demo_client.get(f"/api/series?people={ids}&metrics=steps,sleep_score").json()
    assert all(series["people"][str(p["id"])]["points"] for p in people)
    assert "set-cookie" not in demo_client.get("/api/auth/state").headers


def test_demo_refuses_every_change(demo_client):
    person_id = demo_client.get("/api/auth/state").json()["me"]["id"]
    attempts = [
        ("POST", "/api/auth/setup", {"name": "X", "username": "x", "password": "long-enough"}),
        ("POST", "/api/auth/login", {"username": "x", "password": "long-enough"}),
        ("POST", "/api/people", {"name": "Intruder"}),
        ("PUT", f"/api/people/{person_id}/garmin-key", {"api_key": "not-a-real-key"}),
        ("PATCH", f"/api/people/{person_id}", {"name": "Renamed"}),
        ("POST", f"/api/people/{person_id}/sync", None),
        ("POST", "/api/goals", {"person_id": person_id, "metric_key": "steps", "target": 1}),
        ("DELETE", "/api/demo", None),
    ]
    for method, path, body in attempts:
        response = demo_client.request(method, path, json=body)
        assert response.status_code == 403, (method, path)
        assert "read-only demo" in response.json()["detail"]
    with session_scope() as db:
        assert {p.name for p in db.query(Person)} == {"Alex (demo)", "Sam (demo)"}


def test_demo_mode_wont_start_with_real_people(demo_app):
    with session_scope() as db:
        db.add(Person(name="Real person"))
    with pytest.raises(RuntimeError, match="without real people"), TestClient(demo_app):
        pass


def test_normal_mode_reports_demo_mode_off(client):
    assert client.get("/api/auth/state").json()["demo_mode"] is False
