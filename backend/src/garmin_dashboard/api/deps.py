"""Shared request dependencies: database session, current user and access rules."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CATEGORIES, AuthSession, Person, utcnow
from ..security import hash_token

SESSION_COOKIE = "gd_session"
# Every state-changing request must carry this header. Browsers won't add custom headers
# to cross-site form posts, so this blocks CSRF without a token dance.
CSRF_HEADER = "X-GD-Request"

DB = Annotated[Session, Depends(get_db)]


def current_person(
    db: DB, gd_session: Annotated[str | None, Cookie()] = None
) -> Person:
    if not gd_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    session = db.get(AuthSession, hash_token(gd_session))
    if session is None or session.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    person = db.get(Person, session.person_id)
    if person is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account removed")
    return person


Me = Annotated[Person, Depends(current_person)]


def require_admin(me: Me) -> Person:
    if not me.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return me


Admin = Annotated[Person, Depends(require_admin)]


def can_manage(me: Person, person: Person) -> bool:
    """Self, or an admin managing someone who doesn't sign in themselves (or a demo profile)."""
    return me.id == person.id or (me.is_admin and (person.username is None or person.is_demo))


def visible_categories(viewer: Person, person: Person) -> list[str]:
    if viewer.id == person.id:
        return list(CATEGORIES)
    return [c for c in CATEGORIES if c in (person.shared_categories or [])]


def get_person_or_404(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
    return person


def people_param(
    db: DB, people: Annotated[str | None, Query(description="Comma-separated person ids")] = None
) -> list[Person]:
    if not people:
        return list(db.scalars(select(Person).order_by(Person.id)))
    try:
        ids = [int(p) for p in people.split(",") if p.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bad people list") from exc
    return [get_person_or_404(db, pid) for pid in ids]


PeopleParam = Annotated[list[Person], Depends(people_param)]


def date_range(
    start: dt.date | None = None, end: dt.date | None = None, default_days: int = 30
) -> tuple[dt.date, dt.date]:
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=default_days - 1)
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "start is after end")
    if (end - start).days > 366 * 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Range too long")
    return start, end
