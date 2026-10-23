import datetime as dt
from types import SimpleNamespace

import pytest
from garmin_personal_api import HttpError
from sqlalchemy import func, select

from garmin_dashboard.db import session_scope
from garmin_dashboard.garmin import connector as connector_module
from garmin_dashboard.garmin.connector import BadRequestError, GarminConnector, KeyRejectedError
from garmin_dashboard.garmin.sync import (
    DATASETS_BY_NAME,
    RangeDataset,
    chunks_backwards,
    fetch_adaptive,
    store_raw,
    sync_dataset,
)
from garmin_dashboard.models import DailySummary, Person, RawPayload, SyncState

TODAY = dt.date(2026, 10, 23)


def test_chunks_backwards_cover_range_newest_first():
    start = dt.date(2026, 1, 1)
    windows = list(chunks_backwards(start, TODAY, 31))
    assert windows[0][1] == TODAY
    assert windows[-1][0] == start
    for (a, b), (c, d) in zip(windows, windows[1:], strict=False):
        assert d == a - dt.timedelta(days=1)
        assert (b - a).days <= 30 and (d - c).days <= 30


class FakeClient:
    """Answers daily-summary requests, refusing spans longer than ``limit`` days."""

    def __init__(self, limit=365):
        self.limit = limit
        self.calls = []

    def get_daily_summaries(self, start, end):
        self.calls.append((start, end))
        if (end - start).days + 1 > self.limit:
            raise BadRequestError("range too long")
        days = (end - start).days + 1
        return {"data": [
            {"calendarDate": (start + dt.timedelta(days=i)).isoformat(),
             "movement": {"steps": {"value": 1000 + i}}}
            for i in range(days)
        ]}


class FakeConnector:
    def __init__(self, client):
        self.client = client

    def call(self, method, *args, **kwargs):
        return method(*args, **kwargs)


def test_fetch_adaptive_halves_on_400():
    client = FakeClient(limit=10)
    dataset = DATASETS_BY_NAME["daily_summaries"]
    jan1, jan31 = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    parts = fetch_adaptive(FakeConnector(client), dataset, jan1, jan31)
    covered = sorted(d for a, b, _ in parts for d in (a, b))
    assert covered[0] == dt.date(2026, 1, 1) and covered[-1] == dt.date(2026, 1, 31)
    assert all((b - a).days + 1 <= 10 for a, b, _ in parts)


@pytest.fixture
def person_id(settings):
    with session_scope() as db:
        person = Person(name="Test")
        db.add(person)
        db.flush()
        return person.id


def test_sync_dataset_backfills_then_only_refreshes_recent_days(person_id):
    client = FakeClient()
    dataset = RangeDataset("daily_summaries", 60, DATASETS_BY_NAME["daily_summaries"].fetch,
                           DATASETS_BY_NAME["daily_summaries"].parse, DailySummary)
    history_start = TODAY - dt.timedelta(days=199)

    sync_dataset(FakeConnector(client), person_id, dataset, history_start, TODAY)
    # First request is the most recent window, the rest walk backwards.
    assert client.calls[0][1] == TODAY
    assert client.calls[-1][0] == history_start
    with session_scope() as db:
        state = db.get(SyncState, (person_id, "daily_summaries"))
        assert (state.synced_from, state.synced_through) == (history_start, TODAY)
        assert db.scalar(select(func.count()).select_from(DailySummary)) == 200

    client.calls.clear()
    sync_dataset(FakeConnector(client), person_id, dataset, history_start, TODAY)
    assert client.calls == [(TODAY - dt.timedelta(days=3), TODAY)]


def test_store_raw_drops_superseded_payloads(person_id):
    with session_scope() as db:
        store_raw(db, person_id, "sleep", "2026-10-20..2026-10-22", [1])
        store_raw(db, person_id, "sleep", "2026-09-01..2026-09-30", [2])
        store_raw(db, person_id, "sleep", "2026-10-19..2026-10-23", [3])
    with session_scope() as db:
        keys = sorted(db.scalars(select(RawPayload.key)))
    assert keys == ["2026-09-01..2026-09-30", "2026-10-19..2026-10-23"]


# --- connector retry behaviour -------------------------------------------------------------


class FakeAuth:
    def __init__(self, **_):
        self.forced = 0

    def obtain_token(self, api_key, force_refresh=False):
        if api_key == "bad-key":
            raise HttpError(status_code=401, method="POST", url="u", response_text="nope")
        self.forced += force_refresh
        return SimpleNamespace(access_token=f"token-{self.forced}")

    def close(self):
        pass


class FakeApiClient:
    def __init__(self, token):
        self.token = token

    def update_bearer_token(self, token):
        self.token = token

    def close(self):
        pass


@pytest.fixture
def make_connector(monkeypatch, tmp_path):
    monkeypatch.setattr(connector_module, "PersonalApiAuthenticator", FakeAuth)
    monkeypatch.setattr(connector_module, "GarminPersonalApiClient", FakeApiClient)
    sleeps = []

    def build(key="good-key"):
        conn = GarminConnector(key, tmp_path / "t.json", spacing_seconds=0, sleep=sleeps.append)
        return conn, sleeps

    return build


def _http(status):
    return HttpError(status_code=status, method="GET", url="u", response_text="x")


def test_connector_refreshes_token_once_on_401(make_connector):
    conn, _ = make_connector()
    answers = [_http(401), {"ok": True}]

    def method():
        result = answers.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    assert conn.call(method) == {"ok": True}
    assert conn.client.token == "token-1"


def test_connector_errors(make_connector):
    conn, sleeps = make_connector()

    def raises(status):
        def method():
            raise _http(status)
        return method

    assert conn.call(raises(404)) is None
    with pytest.raises(BadRequestError):
        conn.call(raises(400))
    with pytest.raises(KeyRejectedError):
        conn.call(raises(401))
    with pytest.raises(connector_module.RateLimitedError):
        conn.call(raises(429))
    assert sleeps == [5, 20, 60]


def test_bad_key_is_rejected_up_front(make_connector):
    with pytest.raises(KeyRejectedError):
        make_connector("bad-key")
