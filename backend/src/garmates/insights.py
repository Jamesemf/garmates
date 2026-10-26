"""Weekly digests and pattern-finding over each person's own history.

Insights are deliberately conservative: each needs a minimum number of nights and a
minimum effect size before it is shown, and they are phrased as associations in this
person's data - not causes.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import bucket_start, load_daily, partial_days
from .catalog import METRICS_BY_KEY
from .goals import meets, period_value
from .models import Activity, Goal

DIGEST_METRICS = (
    "sleep_score", "sleep_hours", "hrv", "rhr", "stress_avg", "bb_max",
    "steps", "intensity_minutes", "workouts", "workout_hours", "training_load", "bedtime",
)
COMPARE_WEEKS = 4
MIN_GROUP = 8  # nights per group for a before/after comparison
MIN_PAIRS = 21  # days for a correlation
MIN_EFFECT_D = 0.35
MIN_EFFECT_R = 0.25


def _days(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)


# --- weekly digest -------------------------------------------------------------------------


def last_complete_week(today: dt.date, week_start: str) -> dt.date:
    return bucket_start(today, "week", week_start) - dt.timedelta(days=7)


def weekly_digest(
    db: Session,
    person_id: int,
    week: dt.date,
    week_start: str,
    categories: set[str],
) -> dict:
    """One person's week vs their previous four weeks, plus highlights and goal results."""
    week = bucket_start(week, "week", week_start)
    week_end = week + dt.timedelta(days=6)
    keys = [k for k in DIGEST_METRICS if METRICS_BY_KEY[k].category in categories]
    history_start = week - dt.timedelta(days=7 * COMPARE_WEEKS)
    series = load_daily(db, person_id, keys, history_start, week_end)

    def week_values(key: str, start: dt.date) -> list[float]:
        return [
            series[d][key]
            for d in _days(start, start + dt.timedelta(days=6))
            if d in series and series[d].get(key) is not None
        ]

    metrics = {}
    for key in keys:
        metric = METRICS_BY_KEY[key]
        this_week = period_value(metric, week_values(key, week))
        previous = [
            period_value(metric, week_values(key, week - dt.timedelta(days=7 * i)))
            for i in range(1, COMPARE_WEEKS + 1)
        ]
        previous = [p for p in previous if p is not None]
        usual = statistics.fmean(previous) if previous else None
        is_clock = metric.unit == "clock"
        both = this_week is not None and usual is not None
        metrics[key] = {
            "value": _r(this_week),
            "usual": _r(usual),
            # A percentage of a time of day means nothing; clock metrics move in minutes.
            "delta_pct": _r((this_week - usual) / abs(usual) * 100)
            if both and usual and not is_clock
            else None,
            "delta_minutes": round((this_week - usual) * 60) if both and is_clock else None,
            "days": len(week_values(key, week)),
        }

    if "bedtime" in keys:
        bedtimes = week_values("bedtime", week)
        metrics["bedtime"]["spread_min"] = (
            round(statistics.pstdev(bedtimes) * 60) if len(bedtimes) >= 3 else None
        )

    highlights = _highlights(db, person_id, week, week_end, series, categories)
    notable = _notable_changes(metrics)
    goals = _goal_results(db, person_id, week, week_start, categories)
    return {
        "week": week.isoformat(),
        "week_end": week_end.isoformat(),
        "metrics": metrics,
        "highlights": highlights,
        "notable": notable,
        "goals": goals,
        "has_data": any(m["value"] is not None for m in metrics.values()),
    }


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None or math.isnan(value) else round(value, digits)


def _highlights(
    db: Session,
    person_id: int,
    week: dt.date,
    week_end: dt.date,
    series: dict,
    categories: set[str],
) -> list[dict]:
    out: list[dict] = []
    in_week = {d: v for d, v in series.items() if week <= d <= week_end}

    def extreme(key: str, pick: Callable) -> tuple[dt.date, float] | None:
        pairs = [(d, v[key]) for d, v in in_week.items() if v.get(key) is not None]
        return pick(pairs, key=lambda p: p[1]) if pairs else None

    if "sleep" in categories:
        best, worst = extreme("sleep_score", max), extreme("sleep_score", min)
        if best:
            out.append({"kind": "best_night", "date": best[0].isoformat(), "value": best[1],
                        "metric": "sleep_score"})
        if worst and best and worst[0] != best[0]:
            out.append({"kind": "worst_night", "date": worst[0].isoformat(), "value": worst[1],
                        "metric": "sleep_score"})
    if "activity" in categories:
        active = extreme("steps", max)
        if active:
            out.append({"kind": "most_active_day", "date": active[0].isoformat(),
                        "value": active[1], "metric": "steps"})
    if "workouts" in categories:
        acts = db.scalars(
            select(Activity).where(
                Activity.person_id == person_id, Activity.date >= week, Activity.date <= week_end
            )
        ).all()
        if acts:
            biggest = max(acts, key=lambda a: (a.training_load or 0, a.duration_s or 0))
            out.append({"kind": "biggest_workout", "date": biggest.date.isoformat(),
                        "activity_id": biggest.activity_id, "name": biggest.name,
                        "sport": biggest.sport, "duration_s": biggest.duration_s,
                        "distance_m": biggest.distance_m, "training_load": biggest.training_load})
            for pr in (a for a in acts if a.is_pr):
                out.append({"kind": "personal_record", "date": pr.date.isoformat(),
                            "activity_id": pr.activity_id, "name": pr.name, "sport": pr.sport})
    return out


def _notable_changes(metrics: dict[str, dict]) -> list[dict]:
    notable = []
    for key, entry in metrics.items():
        metric = METRICS_BY_KEY[key]
        delta = entry.get("delta_pct")
        if delta is None or metric.direction == "none" or abs(delta) < 8:
            continue
        good = (delta > 0) == (metric.direction == "up")
        notable.append({"metric": key, "delta_pct": delta, "good": good})
    return sorted(notable, key=lambda n: -abs(n["delta_pct"]))[:4]


def _goal_results(
    db: Session, person_id: int, week: dt.date, week_start: str, categories: set[str]
) -> list[dict]:
    week_end = week + dt.timedelta(days=6)
    results = []
    for goal in db.scalars(select(Goal).where(Goal.person_id == person_id)):
        metric = METRICS_BY_KEY.get(goal.metric_key)
        if metric is None or metric.category not in categories or goal.period == "month":
            continue
        series = load_daily(db, person_id, [metric.key], week, week_end)
        values = {d: v[metric.key] for d, v in series.items() if v.get(metric.key) is not None}
        if goal.period == "day":
            met_days = sum(1 for v in values.values() if meets(goal, v))
            results.append({"goal_id": goal.id, "metric": goal.metric_key, "period": "day",
                            "comparison": goal.comparison, "target": goal.target,
                            "met_days": met_days, "days": len(values)})
        else:
            value = period_value(metric, list(values.values()))
            met = None if value is None else meets(goal, value)
            results.append({"goal_id": goal.id, "metric": goal.metric_key, "period": "week",
                            "comparison": goal.comparison, "target": goal.target,
                            "value": _r(value), "met": met})
    return results


# --- insights --------------------------------------------------------------------------------


def cohens_d(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    pooled = math.sqrt(
        ((len(a) - 1) * statistics.variance(a) + (len(b) - 1) * statistics.variance(b))
        / (len(a) + len(b) - 2)
    )
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled if pooled > 0 else None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return None


def strength(value: float, kind: str) -> str:
    size = abs(value)
    if kind == "d":
        return "strong" if size >= 0.8 else "moderate" if size >= 0.5 else "small"
    return "strong" if size >= 0.5 else "moderate" if size >= 0.35 else "weak"


INSIGHT_METRICS = (
    "sleep_score", "deep_hours", "hrv", "rhr", "bb_max", "steps", "stress_avg", "bedtime",
    "sleep_hours", "workouts",
)


def find_insights(
    db: Session, person_id: int, end: dt.date, days: int, categories: set[str]
) -> list[dict]:
    start = end - dt.timedelta(days=days - 1)
    keys = [k for k in INSIGHT_METRICS if METRICS_BY_KEY[k].category in categories]
    series = load_daily(db, person_id, keys, start - dt.timedelta(days=1), end)
    partial = partial_days(db, person_id, start - dt.timedelta(days=1), end)

    def value(day: dt.date, key: str) -> float | None:
        # A half-recorded day's totals (steps…) would look like a lazy day.
        if day in partial and METRICS_BY_KEY[key].agg == "sum":
            return None
        return series.get(day, {}).get(key)

    insights: list[dict] = []

    def group_insight(
        insight_id: str,
        title: str,
        outcome: str,
        split: Callable[[dt.date], bool | None],
        labels: tuple[str, str],
        lag_days: int = 0,
    ) -> None:
        """Compare an outcome on days where split() is True vs False."""
        if outcome not in keys:
            return
        a, b = [], []
        for day in _days(start, end):
            group = split(day - dt.timedelta(days=lag_days))
            result = value(day, outcome)
            if group is None or result is None:
                continue
            (a if group else b).append(result)
        if len(a) < MIN_GROUP or len(b) < MIN_GROUP:
            return
        d = cohens_d(a, b)
        if d is None or abs(d) < MIN_EFFECT_D:
            return
        metric = METRICS_BY_KEY[outcome]
        insights.append({
            "id": insight_id,
            "kind": "groups",
            "title": title,
            "outcome": outcome,
            "groups": [
                {"label": labels[0], "mean": _r(statistics.fmean(a)), "n": len(a)},
                {"label": labels[1], "mean": _r(statistics.fmean(b)), "n": len(b)},
            ],
            "effect": round(d, 2),
            "strength": strength(d, "d"),
            "favourable": (d > 0) == (metric.direction == "up") if metric.direction != "none"
            else None,
        })

    def correlation_insight(
        insight_id: str,
        title: str,
        x_key: str,
        y_key: str,
        phrases: tuple[str, str],
        lag: int = 0,
    ) -> None:
        """Correlate x (``lag`` days earlier) with y; phrases = (positive r, negative r)."""
        if x_key not in keys or y_key not in keys:
            return
        points = []
        for day in _days(start, end):
            x, y = value(day - dt.timedelta(days=lag), x_key), value(day, y_key)
            if x is not None and y is not None:
                points.append([x, y])
        if len(points) < MIN_PAIRS:
            return
        r = pearson([p[0] for p in points], [p[1] for p in points])
        if r is None or abs(r) < MIN_EFFECT_R:
            return
        insights.append({
            "id": insight_id,
            "kind": "correlation",
            "title": title,
            "x": x_key,
            "y": y_key,
            "r": round(r, 2),
            "n": len(points),
            "summary": phrases[0] if r > 0 else phrases[1],
            "strength": strength(r, "r"),
            "points": [[_r(x), _r(y)] for x, y in points],
        })

    def worked_out(day: dt.date) -> bool | None:
        count = value(day, "workouts")
        return None if count is None else count > 0

    group_insight("workout_sleep", "Sleep after workout days", "sleep_score", worked_out,
                  ("After a workout", "After a rest day"), lag_days=1)
    group_insight("workout_deep", "Deep sleep after workout days", "deep_hours", worked_out,
                  ("After a workout", "After a rest day"), lag_days=1)
    group_insight("workout_hrv", "Overnight HRV after workout days", "hrv", worked_out,
                  ("After a workout", "After a rest day"), lag_days=1)

    bedtimes = [v["bedtime"] for v in series.values() if v.get("bedtime") is not None]
    if len(bedtimes) >= MIN_GROUP * 2:
        median_bed = statistics.median(bedtimes)

        def late(day: dt.date) -> bool | None:
            bed = value(day, "bedtime")
            return None if bed is None else bed > median_bed + 0.25

        group_insight("late_hrv", "Overnight HRV after a late night", "hrv", late,
                      ("Later than usual", "Usual or earlier"))
        group_insight("late_rhr", "Resting heart rate after a late night", "rhr", late,
                      ("Later than usual", "Usual or earlier"))
        # A sleep record dated D started the evening of D-1, hence the one-day lag.
        group_insight("weekend_bedtime", "Weekend vs weekday bedtime", "bedtime",
                      lambda evening: evening.weekday() in (4, 5),
                      ("Fri & Sat nights", "Other nights"), lag_days=1)

    correlation_insight(
        "bedtime_score", "Bedtime and sleep score", "bedtime", "sleep_score",
        ("Later bedtimes went with higher sleep scores.",
         "Later bedtimes went with lower sleep scores."),
    )
    correlation_insight(
        "steps_score", "Daily steps and that night's sleep", "steps", "sleep_score",
        ("More active days were followed by better sleep scores.",
         "More active days were followed by lower sleep scores."),
        lag=1,
    )
    correlation_insight(
        "stress_score", "Daytime stress and that night's sleep", "stress_avg", "sleep_score",
        ("More stressful days were followed by higher sleep scores.",
         "More stressful days were followed by lower sleep scores."),
        lag=1,
    )
    correlation_insight(
        "sleep_bb", "Sleep duration and next-day Body Battery", "sleep_hours", "bb_max",
        ("Longer nights went with a higher Body Battery peak the next day.",
         "Longer nights went with a lower Body Battery peak the next day."),
    )
    return insights
