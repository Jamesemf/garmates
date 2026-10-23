"""Weekly digest and personal insights."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from ..catalog import METRICS_BY_KEY
from ..insights import find_insights, last_complete_week, weekly_digest
from .deps import DB, Me, PeopleParam, visible_categories

router = APIRouter(prefix="/api", tags=["insights"])

WeekStart = Literal["monday", "sunday"]


@router.get("/digest")
def digest(
    me: Me,
    db: DB,
    people: PeopleParam,
    week: dt.date | None = None,
    week_start: WeekStart = "monday",
) -> dict:
    """Each person's week (default: the last complete one) against their previous four."""
    week = week or last_complete_week(dt.date.today(), week_start)
    out = {}
    for person in people:
        categories = set(visible_categories(me, person))
        out[str(person.id)] = weekly_digest(db, person.id, week, week_start, categories)
    first = next(iter(out.values()), None)
    return {
        "week": first["week"] if first else week.isoformat(),
        "week_end": first["week_end"] if first else (week + dt.timedelta(days=6)).isoformat(),
        "people": out,
    }


@router.get("/insights")
def insights(
    me: Me,
    db: DB,
    people: PeopleParam,
    days: Annotated[int, Query(ge=30, le=365)] = 90,
) -> dict:
    today = dt.date.today()
    out = {}
    for person in people:
        categories = set(visible_categories(me, person))
        found = find_insights(db, person.id, today, days, categories)
        # Only show patterns whose every metric is shared with the viewer.
        out[str(person.id)] = [
            i
            for i in found
            if all(
                METRICS_BY_KEY[k].category in categories
                for k in (i.get("outcome"), i.get("x"), i.get("y"))
                if k
            )
        ]
    return {"days": days, "people": out}
