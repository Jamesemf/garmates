from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from garmates import config, security
from garmates.db import init_engine


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMATES_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GARMATES_FRONTEND_DIST", str(tmp_path / "no-frontend"))
    monkeypatch.setenv("GARMATES_REQUEST_SPACING_SECONDS", "0")
    monkeypatch.delenv("GARMATES_SECRET_KEY", raising=False)
    config.get_settings.cache_clear()
    security._fernet.cache_clear()
    current = config.get_settings()
    current.ensure_dirs()
    init_engine(current.database_url)
    yield current
    config.get_settings.cache_clear()
    security._fernet.cache_clear()


@pytest.fixture
def client(settings):
    from garmates.app import create_app

    app = create_app(settings, start_scheduler=False)
    with TestClient(app, headers={"X-Garmates-Request": "1"}) as test_client:
        yield test_client


@pytest.fixture
def admin(client):
    response = client.post(
        "/api/auth/setup",
        json={"name": "James", "username": "james", "password": "correct-horse"},
    )
    assert response.status_code == 200, response.text
    return response.json()
