"""Goal progress (streaks, on-track status) and challenge leaderboards."""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable

from sqlalchemy.orm import Session

from .analytics import bucket_start, load_daily
from .catalog import METRICS_BY_KEY, Metric
from .models import Challenge, Goal

# How many completed periods of history each goal shows.
HISTORY_PERIODS = {"day": 28, "week": 12, "month": 6}
CHALLENGE_BASELINE_DAYS = 30


def _days(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)


def period_bounds(day: dt.date, period: str, week_start: str) -> tuple[dt.date, dt.date]:
    if period == "day":
        return day, day
    if period == "week":
        first = bucket_start(day, "week", week_start)
        return first, first + dt.timedelta(days=6)
    first = day.replace(day=1)
    next_month = (first + dt.timedelta(days=32)).replace(day=1)
    return first, next_month - dt.timedelta(days=1)


def period_value(metric: Metric, values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) if metric.agg == "sum" else statistics.fmean(values)


def meets(goal: Goal, value: float) -> bool:
    return value <= goal.target if goal.comparison == "at_most" else value >= goal.target


def evaluate_goal(db: Session, goal: Goal, today: dt.date, week_start: str) -> dict:
    metric = METRICS_BY_KEY.get(goal.metric_key)
    if metric is None:
        return {"error": f"Unknown metric {goal.metric_key}"}

    current_start, current_end = period_bounds(today, goal.period, week_start)
    first = current_start
    for _ in range(HISTORY_PERIODS[goal.period]):
        first = period_bounds(first - dt.timedelta(days=1), goal.period, week_start)[0]

    series = load_daily(db, goal.person_id, [metric.key], first, today)
    daily = {d: v[metric.key] for d, v in series.items() if v.get(metric.key) is not None}

    def value_for(start: dt.date, end: dt.date) -> float | None:
        return period_value(metric, [daily[d] for d in _days(start, end) if d in daily])

    history = []
    cursor = first
    while cursor < current_start:
        start, end = period_bounds(cursor, goal.period, week_start)
        value = value_for(start, end)
        history.append(
            {
                "start": start.isoformat(),
                "value": None if value is None else round(value, 2),
                "met": None if value is None else meets(goal, value),
            }
        )
        cursor = end + dt.timedelta(days=1)

    last_day = min(current_end, today)
    value = value_for(current_start, last_day)
    elapsed = (last_day - current_start).days + 1
    total = (current_end - current_start).days + 1
    status = _current_status(goal, metric, value, elapsed, total)

    streak = 1 if status == "met" else 0
    for entry in reversed(history):
        if entry["met"]:
            streak += 1
        else:
            break
    judged = [h for h in history if h["met"] is not None]
    return {
        "current": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
            "value": None if value is None else round(value, 2),
            "elapsed_days": elapsed,
            "total_days": total,
            "expected": round(goal.target * elapsed / total, 2) if metric.agg == "sum" else None,
            "status": status,
        },
        "history": history,
        "streak": streak,
        "hit_rate": round(sum(h["met"] for h in judged) / len(judged), 2) if judged else None,
    }


def _current_status(
    goal: Goal, metric: Metric, value: float | None, elapsed: int, total: int
) -> str:
    """met | in_progress | on_track | behind | missed | no_data for the period in progress."""
    if value is None:
        return "no_data"
    if meets(goal, value):
        return "met"
    if goal.period == "day":
        return "in_progress"  # today isn't over; we can't tell the time-of-day pace
    if metric.agg == "sum":
        # Totals accumulate: compare against a straight-line pace through the period.
        if goal.comparison == "at_most":
            return "missed"  # already over a cap that can only grow
        pace = goal.target * elapsed / total
        return "on_track" if value >= pace else "behind"
    # Averages (and single days) can still recover while the period is open.
    return "behind"


# --- challenges ----------------------------------------------------------------------------


def challenge_status(challenge: Challenge, today: dt.date) -> str:
    if today < challenge.start_date:
        return "upcoming"
    if today > challenge.end_date:
        return "finished"
    return "active"


def challenge_board(
    db: Session, challenge: Challenge, visible_ids: set[int], today: dt.date
) -> dict:
    metric = METRICS_BY_KEY[challenge.metric_key]
    status = challenge_status(challenge, today)
    last = min(challenge.end_date, today)
    sign = -1 if metric.direction == "down" else 1

    entries = []
    race: dict[dt.date, dict[str, float]] = {}
    for person_id in challenge.participant_ids:
        if person_id not in visible_ids:
            entries.append({"person_id": person_id, "hidden": True, "score": None, "days": 0})
            continue
        if status == "upcoming":
            entries.append({"person_id": person_id, "hidden": False, "score": None, "days": 0})
            continue
        baseline_start = challenge.start_date - dt.timedelta(days=CHALLENGE_BASELINE_DAYS)
        series = load_daily(db, person_id, [metric.key], baseline_start, last)
        values = {d: v[metric.key] for d, v in series.items() if v.get(metric.key) is not None}
        before = [v for d, v in values.items() if d < challenge.start_date]
        baseline = statistics.fmean(before) if before else None

        running: list[float] = []
        score = None
        for day in _days(challenge.start_date, last):
            if day in values:
                running.append(values[day])
            if not running:
                continue
            if challenge.scoring == "total":
                score = sum(running)
            elif challenge.scoring == "average":
                score = statistics.fmean(running)
            elif baseline:
                score = sign * (statistics.fmean(running) - baseline) / abs(baseline) * 100
            else:
                score = None
            if score is not None:
                race.setdefault(day, {})[f"p{person_id}"] = round(score, 2)
        entries.append(
            {
                "person_id": person_id,
                "hidden": False,
                "score": None if score is None else round(score, 2),
                "days": len(running),
                "baseline": None if baseline is None else round(baseline, 2),
            }
        )

    # Rank: improvement scores are already "higher is better"; otherwise follow the metric.
    better_high = challenge.scoring == "improvement" or metric.direction != "down"
    scored = sorted(
        (e for e in entries if e["score"] is not None),
        key=lambda e: e["score"],
        reverse=better_high,
    )
    for rank, entry in enumerate(scored, start=1):
        entry["rank"] = rank
    return {
        "id": challenge.id,
        "name": challenge.name,
        "metric_key": challenge.metric_key,
        "scoring": challenge.scoring,
        "start": challenge.start_date.isoformat(),
        "end": challenge.end_date.isoformat(),
        "status": status,
        "days_left": max(0, (challenge.end_date - today).days + (status != "finished")),
        "created_by": challenge.created_by,
        "entries": sorted(entries, key=lambda e: e.get("rank", 99)),
        "race": [{"date": d.isoformat(), **values} for d, values in sorted(race.items())],
    }
