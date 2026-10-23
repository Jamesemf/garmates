"""Queries behind the charts: daily series, rollups, baseline comparisons, workout stats."""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import METRICS_BY_KEY, Metric
from .models import Activity, DailySummary, FitnessAge, Hrv, Sleep, SyncState, Weight

Series = dict[dt.date, dict[str, float | None]]

_TABLES = {
    "daily": DailySummary,
    "sleep": Sleep,
    "hrv": Hrv,
    "weight": Weight,
    "fitness_age": FitnessAge,
}


def _days(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)


def _scaled(metric: Metric, value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * metric.scale, max(metric.decimals, 2))


def clock_hours(moment: dt.datetime, anchor: dt.date) -> float:
    """Hours after midnight at the start of ``anchor``.

    Bedtimes are anchored to the evening before the wake-up day, so 22:45 is 22.75 and 00:30
    is 24.5 and a week of bedtimes either side of midnight averages sensibly. Wake times are
    anchored to the wake-up day itself (06:30 is 6.5).
    """
    return (moment - dt.datetime.combine(anchor, dt.time())).total_seconds() / 3600


def synced_through(db: Session, person_id: int) -> dt.date | None:
    return db.scalar(
        select(func.max(SyncState.synced_through)).where(SyncState.person_id == person_id)
    )


def load_daily(
    db: Session, person_id: int, metric_keys: Iterable[str], start: dt.date, end: dt.date
) -> Series:
    """``{date: {metric_key: value}}`` in display units for one person."""
    metrics = [METRICS_BY_KEY[k] for k in metric_keys if k in METRICS_BY_KEY]
    series: Series = defaultdict(dict)

    by_source: dict[str, list[Metric]] = defaultdict(list)
    for metric in metrics:
        by_source[metric.source].append(metric)

    for source, table in _TABLES.items():
        wanted = by_source.get(source)
        if not wanted:
            continue
        rows = db.scalars(
            select(table).where(
                table.person_id == person_id, table.date >= start, table.date <= end
            )
        )
        for row in rows:
            for metric in wanted:
                series[row.date][metric.key] = _scaled(metric, getattr(row, metric.column))

    if by_source.get("sleep_timing"):
        rows = db.execute(
            select(Sleep.date, Sleep.start_local, Sleep.end_local).where(
                Sleep.person_id == person_id, Sleep.date >= start, Sleep.date <= end
            )
        )
        for day, bed, wake in rows:
            for metric in by_source["sleep_timing"]:
                if metric.column == "start_local" and bed is not None:
                    hours = clock_hours(bed, day - dt.timedelta(days=1))
                elif metric.column == "end_local" and wake is not None:
                    hours = clock_hours(wake, day)
                else:
                    continue
                series[day][metric.key] = round(hours, 2)

    if by_source.get("derived"):
        rows = db.execute(
            select(
                DailySummary.date,
                DailySummary.intensity_moderate,
                DailySummary.intensity_vigorous,
            ).where(
                DailySummary.person_id == person_id,
                DailySummary.date >= start,
                DailySummary.date <= end,
            )
        )
        for day, moderate, vigorous in rows:
            if moderate is None and vigorous is None:
                continue
            series[day]["intensity_minutes"] = (moderate or 0) + 2 * (vigorous or 0)

    if by_source.get("activities"):
        _load_activity_metrics(db, person_id, by_source["activities"], start, end, series)

    return dict(sorted(series.items()))


def _load_activity_metrics(
    db: Session,
    person_id: int,
    metrics: list[Metric],
    start: dt.date,
    end: dt.date,
    series: Series,
) -> None:
    rows = db.execute(
        select(
            Activity.date,
            func.count(),
            func.sum(Activity.duration_s),
            func.sum(Activity.distance_m),
            func.sum(Activity.training_load),
            func.max(Activity.vo2max),
        )
        .where(Activity.person_id == person_id, Activity.date >= start, Activity.date <= end)
        .group_by(Activity.date)
    )
    per_day = {
        day: {"count": n, "duration_s": dur, "distance_m": dist, "training_load": load,
              "vo2max": vo2}
        for day, n, dur, dist, load, vo2 in rows
    }
    # Days without a workout count as zero up to the last synced day, so weekly
    # totals and per-day averages are honest. Never-synced people get no zeros.
    through = synced_through(db, person_id)
    if through is None:
        return
    for day in _days(start, min(end, through)):
        values = per_day.get(day, {})
        for metric in metrics:
            raw = values.get(metric.column)
            if metric.column == "vo2max":
                if raw is not None:
                    series[day][metric.key] = _scaled(metric, raw)
            else:
                series[day][metric.key] = _scaled(metric, raw or 0)


# --- rollups -------------------------------------------------------------------------------


def bucket_start(day: dt.date, bucket: str, week_start: str = "monday") -> dt.date:
    if bucket == "week":
        offset = (day.weekday() + 1) % 7 if week_start == "sunday" else day.weekday()
        return day - dt.timedelta(days=offset)
    if bucket == "month":
        return day.replace(day=1)
    return day


def rollup(
    series: Series, metric_keys: list[str], bucket: str, week_start: str = "monday"
) -> list[dict]:
    if bucket == "day":
        return [{"date": d.isoformat(), **values} for d, values in series.items()]
    grouped: dict[dt.date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for day, values in series.items():
        target = grouped[bucket_start(day, bucket, week_start)]
        for key, value in values.items():
            if value is not None:
                target[key].append(value)
    out = []
    for start, values in sorted(grouped.items()):
        row: dict = {"date": start.isoformat()}
        for key in metric_keys:
            metric = METRICS_BY_KEY.get(key)
            numbers = values.get(key)
            if not metric or not numbers:
                row[key] = None
            elif metric.agg == "sum":
                row[key] = round(sum(numbers), metric.decimals or 1)
            else:
                row[key] = round(statistics.fmean(numbers), max(metric.decimals, 1))
        out.append(row)
    return out


# --- comparisons ---------------------------------------------------------------------------


def summarise(
    db: Session,
    person_id: int,
    metric_keys: list[str],
    start: dt.date,
    end: dt.date,
    baseline_days: int,
) -> dict[str, dict]:
    """Period average vs the person's own preceding baseline, for each metric."""
    baseline_start = start - dt.timedelta(days=baseline_days)
    series = load_daily(db, person_id, metric_keys, baseline_start, end)
    result = {}
    for key in metric_keys:
        metric = METRICS_BY_KEY.get(key)
        if metric is None:
            continue
        period = [(d, v[key]) for d, v in series.items() if d >= start and v.get(key) is not None]
        base = [v[key] for d, v in series.items() if d < start and v.get(key) is not None]
        value = statistics.fmean(x for _, x in period) if period else None
        baseline = statistics.fmean(base) if base else None
        spread = statistics.stdev(base) if len(base) >= 3 else None
        delta_pct = (
            (value - baseline) / abs(baseline) * 100
            if value is not None and baseline not in (None, 0)
            else None
        )
        z = (
            (value - baseline) / spread
            if value is not None and baseline is not None and spread and spread > 0
            else None
        )
        result[key] = {
            "value": _round(value, metric),
            "latest": _round(period[-1][1], metric) if period else None,
            "latest_date": period[-1][0].isoformat() if period else None,
            "baseline": _round(baseline, metric),
            "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
            "z": round(z, 2) if z is not None else None,
            "n": len(period),
            "baseline_n": len(base),
        }
    return result


def _round(value: float | None, metric: Metric) -> float | None:
    if value is None or math.isnan(value):
        return None
    return round(value, max(metric.decimals, 1))


# --- workouts ------------------------------------------------------------------------------


def workout_stats(
    db: Session,
    person_id: int,
    start: dt.date,
    end: dt.date,
    bucket: str,
    week_start: str = "monday",
) -> dict:
    activities = db.scalars(
        select(Activity)
        .where(Activity.person_id == person_id, Activity.date >= start, Activity.date <= end)
        .order_by(Activity.start_local)
    ).all()

    by_sport: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "hours": 0.0, "km": 0.0, "load": 0.0}
    )
    buckets: dict[dt.date, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "hours": 0.0, "km": 0.0, "load": 0.0})
    )
    zones = [0.0] * 5
    for act in activities:
        period = buckets[bucket_start(act.date, bucket, week_start)]
        for target in (by_sport[act.sport], period[act.sport]):
            target["count"] += 1
            target["hours"] += (act.duration_s or 0) / 3600
            target["km"] += (act.distance_m or 0) / 1000
            target["load"] += act.training_load or 0
        for i, seconds in enumerate(act.hr_zone_s or []):
            if i < 5 and seconds:
                zones[i] += seconds

    def _clean(stats: dict[str, float]) -> dict[str, float]:
        return {k: round(v, 2) for k, v in stats.items()}

    return {
        "by_sport": {sport: _clean(stats) for sport, stats in by_sport.items()},
        "buckets": [
            {"date": day.isoformat(), "sports": {s: _clean(v) for s, v in sports.items()}}
            for day, sports in sorted(buckets.items())
        ],
        "zone_minutes": [round(z / 60, 1) for z in zones],
        "load": training_load_series(db, person_id, start, end),
    }


def training_load_series(
    db: Session, person_id: int, start: dt.date, end: dt.date
) -> list[dict]:
    """Acute (7-day) vs chronic (28-day, weekly-equivalent) training load and their ratio.

    Garmin's own acute/chronic load isn't available through the Personal API, so this is an
    approximation built from per-activity training load.
    """
    lookback = start - dt.timedelta(days=27)
    rows = db.execute(
        select(Activity.date, func.sum(Activity.training_load))
        .where(Activity.person_id == person_id, Activity.date >= lookback, Activity.date <= end)
        .group_by(Activity.date)
    )
    daily = {day: load or 0 for day, load in rows}
    if not daily:
        return []
    last = min(end, synced_through(db, person_id) or end)
    out = []
    for day in _days(start, last):
        acute = sum(daily.get(day - dt.timedelta(days=i), 0) for i in range(7))
        chronic = sum(daily.get(day - dt.timedelta(days=i), 0) for i in range(28)) / 4
        out.append(
            {
                "date": day.isoformat(),
                "acute": round(acute, 1),
                "chronic": round(chronic, 1),
                "ratio": round(acute / chronic, 2) if chronic > 0 else None,
            }
        )
    return out
