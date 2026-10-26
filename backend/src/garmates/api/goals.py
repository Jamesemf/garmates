"""Personal goals and household challenges."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from ..catalog import METRICS_BY_KEY
from ..goals import challenge_board, evaluate_goal
from ..models import Challenge, Goal, Person
from .deps import DB, Me, PeopleParam, can_manage, get_person_or_404, visible_categories

router = APIRouter(prefix="/api", tags=["goals"])

WeekStart = Literal["monday", "sunday"]


def _category(metric_key: str) -> str:
    metric = METRICS_BY_KEY.get(metric_key)
    if metric is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown metric {metric_key}")
    return metric.category


def _goal_out(goal: Goal, progress: dict) -> dict:
    return {
        "id": goal.id,
        "person_id": goal.person_id,
        "metric_key": goal.metric_key,
        "comparison": goal.comparison,
        "target": goal.target,
        "period": goal.period,
        **progress,
    }


class GoalIn(BaseModel):
    person_id: int
    metric_key: str
    comparison: Literal["at_least", "at_most"] = "at_least"
    target: float = Field(ge=0)
    period: Literal["day", "week", "month"] = "week"


class GoalUpdate(BaseModel):
    comparison: Literal["at_least", "at_most"] | None = None
    target: float | None = Field(default=None, ge=0)
    period: Literal["day", "week", "month"] | None = None


@router.get("/goals")
def list_goals(me: Me, db: DB, people: PeopleParam, week_start: WeekStart = "monday") -> dict:
    today = dt.date.today()
    out = []
    for person in people:
        categories = set(visible_categories(me, person))
        goals = db.scalars(select(Goal).where(Goal.person_id == person.id).order_by(Goal.id))
        for goal in goals:
            if _category(goal.metric_key) in categories:
                out.append(_goal_out(goal, evaluate_goal(db, goal, today, week_start)))
    return {"goals": out}


@router.post("/goals", status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, me: Me, db: DB, week_start: WeekStart = "monday") -> dict:
    person = get_person_or_404(db, body.person_id)
    if not can_manage(me, person):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only set your own goals")
    _category(body.metric_key)
    goal = Goal(**body.model_dump())
    db.add(goal)
    db.flush()
    return _goal_out(goal, evaluate_goal(db, goal, dt.date.today(), week_start))


def _managed_goal(db: DB, me: Person, goal_id: int) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such goal")
    if not can_manage(me, get_person_or_404(db, goal.person_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your goal")
    return goal


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: int, body: GoalUpdate, me: Me, db: DB, week_start: WeekStart = "monday"
) -> dict:
    goal = _managed_goal(db, me, goal_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(goal, key, value)
    return _goal_out(goal, evaluate_goal(db, goal, dt.date.today(), week_start))


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, me: Me, db: DB) -> dict:
    db.delete(_managed_goal(db, me, goal_id))
    return {"ok": True}


# --- challenges ----------------------------------------------------------------------------


class ChallengeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric_key: str
    scoring: Literal["total", "average", "improvement"] = "total"
    start_date: dt.date
    end_date: dt.date
    participant_ids: list[int] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _check(self) -> ChallengeIn:
        metric = METRICS_BY_KEY.get(self.metric_key)
        if metric is None:
            raise ValueError(f"Unknown metric {self.metric_key}")
        if metric.direction == "none":
            raise ValueError(f"{metric.label} has no better direction, so it can't be a challenge")
        if self.scoring == "total" and metric.agg != "sum":
            raise ValueError(f"{metric.label} isn't a running total - score it by average")
        if self.end_date < self.start_date:
            raise ValueError("The challenge ends before it starts")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Challenges can last at most a year")
        if len(set(self.participant_ids)) != len(self.participant_ids):
            raise ValueError("Each person can only join once")
        return self


@router.get("/challenges")
def list_challenges(me: Me, db: DB) -> dict:
    today = dt.date.today()
    people = {p.id: p for p in db.scalars(select(Person))}
    out = []
    for challenge in db.scalars(select(Challenge).order_by(Challenge.start_date.desc())):
        category = _category(challenge.metric_key)
        if me.id not in challenge.participant_ids and not me.is_admin:
            continue
        visible = {
            pid
            for pid in challenge.participant_ids
            if pid in people and category in visible_categories(me, people[pid])
        }
        out.append(challenge_board(db, challenge, visible, today))
    return {"challenges": out}


@router.post("/challenges", status_code=status.HTTP_201_CREATED)
def create_challenge(body: ChallengeIn, me: Me, db: DB) -> dict:
    category = _category(body.metric_key)
    for pid in body.participant_ids:
        person = get_person_or_404(db, pid)
        # Only people who share this category with you (or yourself) can be challenged.
        if category not in visible_categories(me, person):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{person.name} doesn't share this kind of data with you",
            )
    challenge = Challenge(**body.model_dump(), created_by=me.id)
    db.add(challenge)
    db.flush()
    visible = set(body.participant_ids)
    return challenge_board(db, challenge, visible, dt.date.today())


@router.delete("/challenges/{challenge_id}")
def delete_challenge(challenge_id: int, me: Me, db: DB) -> dict:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such challenge")
    if challenge.created_by != me.id and not me.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its creator can delete a challenge")
    db.delete(challenge)
    return {"ok": True}
