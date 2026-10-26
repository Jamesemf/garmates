"""Household members, their Garmin keys, sharing preferences and sync triggers."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import prefs
from ..config import get_settings
from ..garmin.connector import GarminConnector, GarminError, KeyRejectedError
from ..garmin.sync import reset_sync_state, sync_manager
from ..models import (
    CATEGORIES,
    GarminCredential,
    Person,
    SyncRun,
    SyncState,
    utcnow,
)
from ..security import (
    MIN_PASSWORD_LENGTH,
    encrypt_secret,
    hash_password,
    key_hint,
)
from .deps import DB, Admin, Me, can_manage, get_person_or_404, visible_categories

router = APIRouter(prefix="/api/people", tags=["people"])

PALETTE_SIZE = 8
KEY_WARNING_DAYS = 14


def next_color_slot(db: Session) -> int:
    used = set(db.scalars(select(Person.color_slot)))
    for slot in range(PALETTE_SIZE):
        if slot not in used:
            return slot
    return db.scalar(select(func.count(Person.id))) % PALETTE_SIZE


def person_out(db: Session, person: Person, viewer: Person) -> dict:
    cred = person.credential
    last_run = db.scalar(
        select(SyncRun).where(SyncRun.person_id == person.id).order_by(SyncRun.id.desc()).limit(1)
    )
    managed = can_manage(viewer, person)
    key = None
    if cred is not None:
        days_left = (cred.key_expires_on - dt.date.today()).days if cred.key_expires_on else None
        key = {
            "hint": cred.key_hint if managed else None,
            "status": cred.status,
            "expires_on": cred.key_expires_on.isoformat() if cred.key_expires_on else None,
            "days_left": days_left,
            "expiring_soon": days_left is not None and days_left <= KEY_WARNING_DAYS,
            "last_error": cred.last_error if managed else None,
            "garmin_display_name": cred.garmin_display_name,
        }
    return {
        "id": person.id,
        "name": person.name,
        "color_slot": person.color_slot,
        "is_admin": person.is_admin,
        "is_demo": person.is_demo,
        "is_me": person.id == viewer.id,
        "can_manage": managed,
        "has_login": person.username is not None,
        "username": person.username if managed or viewer.is_admin else None,
        "shared_categories": person.shared_categories or [],
        "visible_categories": visible_categories(viewer, person),
        "history_start": person.history_start.isoformat() if person.history_start else None,
        "preferences": prefs.effective(person.preferences, person.garmin_preferences)
        if managed
        else None,
        "preference_overrides": (person.preferences or {}) if managed else None,
        "key": key,
        "syncing": sync_manager.is_running(person.id),
        "last_sync": None
        if last_run is None
        else {
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat() + "Z",
            "finished_at": last_run.finished_at.isoformat() + "Z" if last_run.finished_at else None,
            "message": last_run.message if managed else None,
        },
    }


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    username: str | None = Field(default=None, min_length=2, max_length=80)
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256)


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color_slot: int | None = Field(default=None, ge=0, lt=PALETTE_SIZE)
    shared_categories: list[str] | None = None
    history_start: dt.date | None = None
    # Partial update; a key set to null goes back to the Garmin/default value.
    preferences: dict[str, str | None] | None = None

    @field_validator("shared_categories")
    @classmethod
    def _known_categories(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(c not in CATEGORIES for c in value):
            raise ValueError(f"categories must be among {CATEGORIES}")
        return value

    @field_validator("preferences")
    @classmethod
    def _known_preferences(cls, value: dict | None) -> dict | None:
        if value is not None:
            prefs.validate(value)
        return value


class KeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)
    expires_on: dt.date | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


def _managed_person(db: Session, me: Person, person_id: int) -> Person:
    person = get_person_or_404(db, person_id)
    if not can_manage(me, person):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only this person can change their own settings once they have a login.",
        )
    return person


@router.get("")
def list_people(me: Me, db: DB) -> list[dict]:
    people = db.scalars(select(Person).order_by(Person.id))
    return [person_out(db, p, me) for p in people]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_person(body: PersonCreate, me: Admin, db: DB) -> dict:
    if (body.username is None) != (body.password is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Give both a username and password, or neither"
        )
    username = body.username.strip().lower() if body.username else None
    if username and db.scalar(select(Person).where(Person.username == username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken")
    person = Person(
        name=body.name.strip(),
        username=username,
        password_hash=hash_password(body.password) if body.password else None,
        color_slot=next_color_slot(db),
    )
    db.add(person)
    db.flush()
    return person_out(db, person, me)


@router.patch("/{person_id}")
def update_person(person_id: int, body: PersonUpdate, me: Me, db: DB) -> dict:
    person = _managed_person(db, me, person_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        person.name = changes["name"].strip()
    if "color_slot" in changes:
        person.color_slot = changes["color_slot"]
    if "shared_categories" in changes:
        person.shared_categories = [c for c in CATEGORIES if c in changes["shared_categories"]]
    if "history_start" in changes:
        person.history_start = changes["history_start"]
    if changes.get("preferences") is not None:
        merged = {**(person.preferences or {}), **changes["preferences"]}
        person.preferences = {k: v for k, v in merged.items() if v is not None} or None
    return person_out(db, person, me)


@router.delete("/{person_id}")
def delete_person(person_id: int, me: Admin, db: DB) -> dict:
    person = get_person_or_404(db, person_id)
    if person.id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete your own account")
    db.delete(person)
    (get_settings().secrets_dir / f"bearer-token-person-{person_id}.json").unlink(missing_ok=True)
    return {"ok": True}


@router.post("/{person_id}/password")
def reset_password(person_id: int, body: PasswordReset, me: Admin, db: DB) -> dict:
    person = get_person_or_404(db, person_id)
    if person.username is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This person has no login")
    person.password_hash = hash_password(body.password)
    return {"ok": True}


@router.put("/{person_id}/garmin-key")
def set_garmin_key(person_id: int, body: KeyIn, me: Me, db: DB) -> dict:
    person = _managed_person(db, me, person_id)
    api_key = body.api_key.strip()
    settings = get_settings()
    settings.ensure_dirs()
    cache_file = settings.secrets_dir / f"bearer-token-person-{person_id}.json"
    cache_file.unlink(missing_ok=True)
    # Validate before storing: exchange the key and read the profile it belongs to.
    try:
        with GarminConnector(api_key, cache_file, spacing_seconds=0) as conn:
            profile = conn.call(conn.client.get_user_profile_settings) or {}
    except KeyRejectedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except GarminError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't verify the key: {exc}") from exc

    cred = person.credential or GarminCredential(person_id=person.id)
    previous_owner = cred.garmin_display_name
    new_owner = profile.get("displayName") if isinstance(profile, dict) else None
    cred.api_key_encrypted = encrypt_secret(api_key)
    cred.key_hint = key_hint(api_key)
    cred.key_expires_on = body.expires_on
    cred.added_at = utcnow()
    cred.status = "ok"
    cred.last_error = None
    cred.last_verified_at = utcnow()
    cred.garmin_display_name = new_owner
    person.credential = cred
    if previous_owner and new_owner and previous_owner != new_owner:
        # A key for a different Garmin account: start that person's sync from scratch.
        reset_sync_state(db, person.id)
    db.flush()
    db.commit()
    sync_manager.submit(person.id)
    return person_out(db, person, me)


@router.delete("/{person_id}/garmin-key")
def remove_garmin_key(person_id: int, me: Me, db: DB) -> dict:
    person = _managed_person(db, me, person_id)
    if person.credential is not None:
        db.delete(person.credential)
    (get_settings().secrets_dir / f"bearer-token-person-{person_id}.json").unlink(missing_ok=True)
    db.flush()
    db.expire(person)
    return person_out(db, person, me)


@router.post("/{person_id}/sync")
def trigger_sync(person_id: int, me: Me, db: DB) -> dict:
    person = _managed_person(db, me, person_id)
    if person.credential is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a Garmin key first")
    started = sync_manager.submit(person.id)
    return {"started": started, "syncing": True}


@router.get("/{person_id}/sync-state")
def sync_state(person_id: int, me: Me, db: DB) -> dict:
    person = _managed_person(db, me, person_id)
    states = db.scalars(select(SyncState).where(SyncState.person_id == person.id))
    runs = db.scalars(
        select(SyncRun).where(SyncRun.person_id == person.id).order_by(SyncRun.id.desc()).limit(10)
    )
    return {
        "syncing": sync_manager.is_running(person.id),
        "datasets": [
            {
                "dataset": s.dataset,
                "synced_from": s.synced_from.isoformat() if s.synced_from else None,
                "synced_through": s.synced_through.isoformat() if s.synced_through else None,
                "last_status": s.last_status,
                "last_error": s.last_error,
            }
            for s in states
        ],
        "runs": [
            {
                "status": r.status,
                "started_at": r.started_at.isoformat() + "Z",
                "finished_at": r.finished_at.isoformat() + "Z" if r.finished_at else None,
                "message": r.message,
            }
            for r in runs
        ],
    }


demo_router = APIRouter(prefix="/api/demo", tags=["demo"])


@demo_router.post("")
def load_demo(_: Admin) -> dict:
    from ..demo import seed_demo  # local import: demo.py imports this module

    return {"ids": seed_demo()}


@demo_router.delete("")
def unload_demo(_: Admin) -> dict:
    from ..demo import remove_demo  # local import: demo.py imports this module

    return {"removed": remove_demo()}


@router.post("/{person_id}/reset-sync")
def reset_sync(person_id: int, me: Me, db: DB) -> dict:
    """Forget sync progress so the next run re-fetches the whole history window."""
    person = _managed_person(db, me, person_id)
    db.execute(delete(SyncState).where(SyncState.person_id == person.id))
    return {"ok": True}
