"""First-run setup, sign in/out and password changes."""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ..config import get_settings
from ..models import AuthSession, Person, utcnow
from ..security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)
from .deps import DB, SESSION_COOKIE, Me, current_person
from .people import next_color_slot, person_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

_FAILURE_WINDOW_S = 15 * 60
_MAX_FAILURES = 10
_failures: dict[str, deque[float]] = defaultdict(deque)
_failures_lock = threading.Lock()


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


def _setup_required(db: DB) -> bool:
    return not db.scalar(select(func.count()).where(Person.password_hash.is_not(None)))


def _start_session(db: DB, response: Response, person: Person) -> None:
    settings = get_settings()
    token, token_hash = new_session_token()
    expires = utcnow() + dt.timedelta(days=settings.session_days)
    db.add(AuthSession(token_hash=token_hash, person_id=person.id, expires_at=expires))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )


def _check_rate_limit(client: str) -> None:
    now = time.monotonic()
    with _failures_lock:
        attempts = _failures[client]
        while attempts and now - attempts[0] > _FAILURE_WINDOW_S:
            attempts.popleft()
        if len(attempts) >= _MAX_FAILURES:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts - try again in 15 minutes"
            )


def _record_failure(client: str) -> None:
    with _failures_lock:
        _failures[client].append(time.monotonic())


@router.get("/state")
def auth_state(request: Request, db: DB) -> dict:
    demo_mode = get_settings().demo_mode
    me = None
    token = request.cookies.get(SESSION_COOKIE)
    if token or demo_mode:
        try:
            me = current_person(db, token)
        except HTTPException:
            me = None
    return {
        "setup_required": not demo_mode and _setup_required(db),
        "demo_mode": demo_mode,
        "me": person_out(db, me, me) if me else None,
    }


@router.post("/setup")
def setup(body: SetupIn, db: DB, response: Response) -> dict:
    if not _setup_required(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed")
    person = Person(
        name=body.name.strip(),
        username=body.username.strip().lower(),
        password_hash=hash_password(body.password),
        is_admin=True,
        color_slot=next_color_slot(db),
    )
    db.add(person)
    db.flush()
    _start_session(db, response, person)
    return person_out(db, person, person)


@router.post("/login")
def login(body: LoginIn, request: Request, db: DB, response: Response) -> dict:
    client = request.client.host if request.client else "unknown"
    _check_rate_limit(client)
    person = db.scalar(select(Person).where(Person.username == body.username.strip().lower()))
    if person is None or not verify_password(person.password_hash, body.password):
        _record_failure(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    _start_session(db, response, person)
    return person_out(db, person, person)


@router.post("/logout")
def logout(request: Request, db: DB, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(body: PasswordIn, me: Me, db: DB) -> dict:
    if not verify_password(me.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    me.password_hash = hash_password(body.new_password)
    return {"ok": True}
