"""Pull each person's Garmin data into the local database.

Strategy per date-range dataset:

1. *Catch up*: fetch from shortly before ``synced_through`` up to today, because Garmin
   keeps revising the most recent days (late uploads, sleep re-scoring).
2. *Backfill*: walk backwards from ``synced_from`` towards the person's history start,
   newest chunk first, so recent data shows up on the dashboard within seconds and older
   history fills in over the rest of the run (resumable if interrupted).

Each request is limited to Garmin's documented maximum span; if Garmin still answers 400
the span is halved and retried.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import (
    Activity,
    DailySummary,
    FitnessAge,
    GarminCredential,
    Hrv,
    Person,
    RawPayload,
    Sleep,
    SyncRun,
    SyncState,
    Weight,
    utcnow,
)
from ..security import decrypt_secret
from . import parsers
from .connector import BadRequestError, GarminConnector, GarminError, KeyRejectedError

_LOGGER = logging.getLogger(__name__)

ACTIVITY_PAGE_SIZE = 100


@dataclass(frozen=True)
class RangeDataset:
    name: str
    max_days: int  # inclusive span per request
    fetch: Callable[[GarminConnector, dt.date, dt.date], Any]
    parse: Callable[[Any], list[dict]]
    model: type


def _fetch_activities(conn: GarminConnector, start: dt.date, end: dt.date) -> list:
    items: list = []
    offset = 0
    while True:
        page = conn.call(
            conn.client.search_activities,
            start=offset,
            limit=ACTIVITY_PAGE_SIZE,
            start_date=start,
            end_date=end,
        )
        page = page or []
        items.extend(page)
        if len(page) < ACTIVITY_PAGE_SIZE:
            return items
        offset += ACTIVITY_PAGE_SIZE


RANGE_DATASETS: tuple[RangeDataset, ...] = (
    RangeDataset(
        "daily_summaries",
        365,
        lambda c, a, b: c.call(c.client.get_daily_summaries, a, b),
        parsers.parse_daily_summaries,
        DailySummary,
    ),
    RangeDataset(
        "sleep",
        31,
        lambda c, a, b: c.call(c.client.get_daily_sleep_summaries, a, b),
        parsers.parse_sleep_summaries,
        Sleep,
    ),
    RangeDataset(
        "hrv",
        31,
        lambda c, a, b: c.call(c.client.get_daily_hrv_summaries, a, b),
        parsers.parse_hrv_summaries,
        Hrv,
    ),
    RangeDataset(
        "weight",
        90,
        lambda c, a, b: c.call(c.client.get_weight_measurements, a, b),
        parsers.parse_weight_range,
        Weight,
    ),
    RangeDataset("activities", 90, _fetch_activities, parsers.parse_activities, Activity),
)
DATASETS_BY_NAME = {ds.name: ds for ds in RANGE_DATASETS}


# --- storage -------------------------------------------------------------------------------


def _range_key(start: dt.date, end: dt.date) -> str:
    return f"{start.isoformat()}..{end.isoformat()}"


def _parse_range_key(key: str) -> tuple[dt.date, dt.date] | None:
    try:
        first, last = key.split("..")
        return dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    except ValueError:
        return None


def store_raw(
    db: Session, person_id: int, dataset: str, key: str, payload: Any
) -> None:
    """Keep the verbatim response; drop older payloads whose range this one supersedes."""
    new_range = _parse_range_key(key)
    if new_range is not None:
        existing = db.scalars(
            select(RawPayload).where(
                RawPayload.person_id == person_id, RawPayload.dataset == dataset
            )
        ).all()
        for row in existing:
            old = _parse_range_key(row.key)
            if old and new_range[0] <= old[0] and old[1] <= new_range[1] and row.key != key:
                db.delete(row)
    stmt = sqlite_insert(RawPayload).values(
        person_id=person_id,
        dataset=dataset,
        key=key,
        fetched_at=utcnow(),
        payload=json.dumps(payload, separators=(",", ":")),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["person_id", "dataset", "key"],
        set_={"payload": stmt.excluded.payload, "fetched_at": stmt.excluded.fetched_at},
    )
    db.execute(stmt)


def upsert_rows(db: Session, model: type, person_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    table = model.__table__
    pk_cols = [col.name for col in table.primary_key.columns]
    for row in rows:
        values = {**row, "person_id": person_id}
        stmt = sqlite_insert(model).values(**values)
        updates = {k: stmt.excluded[k] for k in values if k not in pk_cols}
        db.execute(stmt.on_conflict_do_update(index_elements=pk_cols, set_=updates))
    return len(rows)


# --- chunking ------------------------------------------------------------------------------


def chunks_backwards(start: dt.date, end: dt.date, span: int) -> Iterator[tuple[dt.date, dt.date]]:
    """Inclusive [a, b] windows of at most ``span`` days, newest first."""
    cursor = end
    while cursor >= start:
        first = max(start, cursor - dt.timedelta(days=span - 1))
        yield first, cursor
        cursor = first - dt.timedelta(days=1)


def fetch_adaptive(
    conn: GarminConnector, dataset: RangeDataset, start: dt.date, end: dt.date
) -> list[tuple[dt.date, dt.date, Any]]:
    """Fetch [start, end]; on HTTP 400 split the window in half and retry each part."""
    try:
        return [(start, end, dataset.fetch(conn, start, end))]
    except BadRequestError:
        if start == end:
            raise
        middle = start + (end - start) // 2
        _LOGGER.info("%s: 400 for %s..%s, splitting", dataset.name, start, end)
        return fetch_adaptive(conn, dataset, start, middle) + fetch_adaptive(
            conn, dataset, middle + dt.timedelta(days=1), end
        )


# --- orchestration -------------------------------------------------------------------------


class SyncAborted(Exception):
    pass


def _state(db: Session, person_id: int, dataset: str) -> SyncState:
    state = db.get(SyncState, (person_id, dataset))
    if state is None:
        state = SyncState(person_id=person_id, dataset=dataset)
        db.add(state)
    return state


def sync_dataset(
    conn: GarminConnector,
    person_id: int,
    dataset: RangeDataset,
    history_start: dt.date,
    today: dt.date,
) -> int:
    """Catch up then backfill one dataset. Commits after every window. Returns rows saved."""
    settings = get_settings()
    saved = 0

    with session_scope() as db:
        synced_through = _state(db, person_id, dataset.name).synced_through

    def save(windows: list[tuple[dt.date, dt.date, Any]], *, extend: str) -> None:
        nonlocal saved
        with session_scope() as db:
            state = _state(db, person_id, dataset.name)
            for first, last, payload in windows:
                if payload is not None:
                    store_raw(db, person_id, dataset.name, _range_key(first, last), payload)
                    saved += upsert_rows(db, dataset.model, person_id, dataset.parse(payload))
                if extend == "forward":
                    state.synced_through = max(state.synced_through or last, last)
                    state.synced_from = min(state.synced_from or first, first)
                else:
                    state.synced_from = min(state.synced_from or first, first)
            state.last_run_at = utcnow()

    # 1. catch up recent days
    if synced_through is None:
        catch_up_start = max(history_start, today - dt.timedelta(days=dataset.max_days - 1))
    else:
        catch_up_start = max(
            history_start, synced_through - dt.timedelta(days=settings.resync_recent_days)
        )
    for first, last in chunks_backwards(catch_up_start, today, dataset.max_days):
        save(fetch_adaptive(conn, dataset, first, last), extend="forward")

    # 2. backfill older history, newest first
    with session_scope() as db:
        oldest = _state(db, person_id, dataset.name).synced_from
    if oldest is not None and oldest > history_start:
        backfill_end = oldest - dt.timedelta(days=1)
        for first, last in chunks_backwards(history_start, backfill_end, dataset.max_days):
            save(fetch_adaptive(conn, dataset, first, last), extend="backward")
    return saved


def sync_snapshots(conn: GarminConnector, person_id: int, today: dt.date) -> None:
    """Small 'current state' endpoints fetched once per run."""
    profile = conn.call(conn.client.get_user_profile_settings)
    zones = conn.call(conn.client.get_heart_rate_zones)
    fitness = conn.call(conn.client.get_fitness_age, today)
    with session_scope() as db:
        if profile is not None:
            store_raw(db, person_id, "profile", "current", profile)
            cred = db.get(GarminCredential, person_id)
            if cred is not None and isinstance(profile, dict):
                cred.garmin_display_name = profile.get("displayName")
        if zones is not None:
            store_raw(db, person_id, "hr_zones", "current", zones)
        if fitness is not None:
            store_raw(db, person_id, "fitness_age", today.isoformat(), fitness)
            upsert_rows(db, FitnessAge, person_id, parsers.parse_fitness_age(fitness, today))


def open_connector(person_id: int) -> GarminConnector:
    settings = get_settings()
    with session_scope() as db:
        cred = db.get(GarminCredential, person_id)
        if cred is None:
            raise SyncAborted("No Garmin key has been added for this person yet.")
        api_key = decrypt_secret(cred.api_key_encrypted)
    settings.ensure_dirs()
    return GarminConnector(
        api_key,
        settings.secrets_dir / f"bearer-token-person-{person_id}.json",
        spacing_seconds=settings.request_spacing_seconds,
    )


def _set_credential_status(person_id: int, status: str, error: str | None) -> None:
    with session_scope() as db:
        cred = db.get(GarminCredential, person_id)
        if cred is None:
            return
        cred.status = status
        cred.last_error = error
        if status == "ok":
            cred.last_verified_at = utcnow()


def sync_person(person_id: int, datasets: list[str] | None = None) -> str:
    """Run a full sync for one person. Returns the run status (ok|partial|error)."""
    settings = get_settings()
    today = dt.date.today()
    with session_scope() as db:
        person = db.get(Person, person_id)
        if person is None:
            raise SyncAborted(f"Unknown person {person_id}")
        history_start = person.history_start or (
            today - dt.timedelta(days=settings.default_history_days)
        )
        run = SyncRun(person_id=person_id)
        db.add(run)
        db.flush()
        run_id = run.id

    errors: list[str] = []
    status = "ok"
    try:
        with open_connector(person_id) as conn:
            _set_credential_status(person_id, "ok", None)
            sync_snapshots(conn, person_id, today)
            for dataset in RANGE_DATASETS:
                if datasets and dataset.name not in datasets:
                    continue
                try:
                    sync_dataset(conn, person_id, dataset, history_start, today)
                    _record_dataset(person_id, dataset.name, "ok", None)
                except KeyRejectedError:
                    raise
                except GarminError as exc:
                    errors.append(f"{dataset.name}: {exc}")
                    _record_dataset(person_id, dataset.name, "error", str(exc))
        if errors:
            status = "partial"
    except KeyRejectedError as exc:
        status = "error"
        errors.append(str(exc))
        _set_credential_status(person_id, "invalid", str(exc))
    except (GarminError, SyncAborted) as exc:
        status = "error"
        errors.append(str(exc))
    except Exception as exc:  # keep the scheduler alive; surface the failure in the UI
        _LOGGER.exception("Sync crashed for person %s", person_id)
        status = "error"
        errors.append(f"Unexpected error: {exc}")

    with session_scope() as db:
        run = db.get(SyncRun, run_id)
        run.finished_at = utcnow()
        run.status = status
        run.message = "\n".join(errors) or None
    return status


def _record_dataset(person_id: int, dataset: str, status: str, error: str | None) -> None:
    with session_scope() as db:
        state = _state(db, person_id, dataset)
        state.last_status = status
        state.last_error = error
        state.last_run_at = utcnow()


def reparse_all(person_id: int | None = None) -> int:
    """Rebuild normalised tables from stored raw payloads (after a parser fix)."""
    count = 0
    with session_scope() as db:
        query = select(RawPayload).order_by(RawPayload.fetched_at)
        if person_id is not None:
            query = query.where(RawPayload.person_id == person_id)
        for raw in db.scalars(query):
            payload = json.loads(raw.payload)
            dataset = DATASETS_BY_NAME.get(raw.dataset)
            if dataset is not None:
                count += upsert_rows(db, dataset.model, raw.person_id, dataset.parse(payload))
            elif raw.dataset == "fitness_age":
                as_of = dt.date.fromisoformat(raw.key)
                count += upsert_rows(
                    db, FitnessAge, raw.person_id, parsers.parse_fitness_age(payload, as_of)
                )
    return count


def reset_sync_state(db: Session, person_id: int) -> None:
    db.execute(delete(SyncState).where(SyncState.person_id == person_id))


# --- background execution ------------------------------------------------------------------


class SyncManager:
    """Runs syncs off the request thread, at most one at a time per person."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sync")
        self._lock = threading.Lock()
        self._running: set[int] = set()

    def is_running(self, person_id: int) -> bool:
        with self._lock:
            return person_id in self._running

    def running(self) -> set[int]:
        with self._lock:
            return set(self._running)

    def submit(self, person_id: int) -> bool:
        with self._lock:
            if person_id in self._running:
                return False
            self._running.add(person_id)
        self._executor.submit(self._run, person_id)
        return True

    def _run(self, person_id: int) -> None:
        try:
            sync_person(person_id)
        except Exception:
            _LOGGER.exception("Background sync failed for person %s", person_id)
        finally:
            with self._lock:
                self._running.discard(person_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


sync_manager = SyncManager()
