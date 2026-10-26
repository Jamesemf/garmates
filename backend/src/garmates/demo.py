"""Synthetic demo profiles so the dashboard can be explored before any Garmin key is added.

Payloads are generated in the Personal API's own JSON shapes and pushed through the real
parsers, so the demo also exercises the ingest pipeline end to end.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass

from sqlalchemy import select

from .api.people import next_color_slot
from .db import session_scope
from .garmin import parsers
from .garmin.sync import DATASETS_BY_NAME, store_raw, upsert_rows
from .models import ActivityTrack, FitnessAge, Person, SyncState, utcnow

DEMO_DAYS = 240


@dataclass(frozen=True)
class Profile:
    name: str
    seed: int
    rhr: float
    hrv: float
    sleep_h: float
    steps: float
    weight_kg: float
    age: int
    # (weekday, sport type key, minutes, km) - a typical training week
    week: tuple[tuple[int, str, int, float], ...]
    home: tuple[float, float]


PROFILES = (
    Profile(
        "Alex (demo)", 7, 51, 68, 7.1, 11500, 72.0, 36,
        ((1, "running", 45, 8.5), (3, "running", 35, 6.5), (5, "strength_training", 40, 0),
         (6, "running", 95, 18.0)),
        (51.5074, -0.1657),
    ),
    Profile(
        "Sam (demo)", 11, 58, 47, 7.6, 8800, 63.5, 34,
        ((0, "strength_training", 45, 0), (2, "road_biking", 75, 32.0), (4, "walking", 50, 4.2),
         (5, "road_biking", 120, 55.0)),
        (51.5033, -0.1196),
    ),
)


def _epoch_ms(moment: dt.datetime) -> int:
    """Garmin's *Local* timestamps: local wall-clock time encoded as if it were UTC."""
    return int(moment.replace(tzinfo=dt.UTC).timestamp() * 1000)


def _real_epoch_ms(moment: dt.datetime) -> int:
    """True instant for a naive local time (intraday series are real GMT epochs)."""
    return int(moment.timestamp() * 1000)


def _generate(profile: Profile, today: dt.date) -> dict:
    rng = random.Random(profile.seed)
    start = today - dt.timedelta(days=DEMO_DAYS - 1)
    fitness_trend = 0.0
    load_7d: list[float] = []

    daily, sleeps, hrvs, weights, activities, tracks, day_details = [], [], [], [], [], [], {}
    weight = profile.weight_kg + 2.0
    next_id = profile.seed * 10_000_000

    for i in range(DEMO_DAYS):
        day = start + dt.timedelta(days=i)
        weekend = day.weekday() >= 5
        fitness_trend = min(1.0, fitness_trend + 0.004)  # slow improvement over the period
        fatigue = sum(load_7d[-3:]) / 600 if load_7d else 0
        illness = 1.0 if 140 <= i < 145 and profile.seed == 7 else 0.0  # a short cold for Alex

        rhr = profile.rhr - 2.5 * fitness_trend + 2.2 * fatigue + 6 * illness + rng.gauss(0, 1.3)
        hrv = profile.hrv + 5 * fitness_trend - 7 * fatigue - 15 * illness + rng.gauss(0, 4.5)
        sleep_h = profile.sleep_h + (0.5 if weekend else 0) - 0.6 * illness + rng.gauss(0, 0.55)
        sleep_s = int(max(4.2, sleep_h) * 3600)
        deep = int(sleep_s * rng.uniform(0.15, 0.22))
        rem = int(sleep_s * rng.uniform(0.18, 0.25))
        awake = int(rng.uniform(8, 35) * 60)
        light = sleep_s - deep - rem
        score = max(35, min(97, int(55 + (sleep_h - 6) * 11 + (hrv - profile.hrv) * 0.4
                                    + rng.gauss(0, 5))))
        qualifier = "EXCELLENT" if score >= 90 else "GOOD" if score >= 80 else (
            "FAIR" if score >= 60 else "POOR")
        bedtime = dt.datetime.combine(day - dt.timedelta(days=1), dt.time(22, 45)) + dt.timedelta(
            minutes=rng.gauss(0, 35) + (40 if weekend else 0)
        )
        wake = bedtime + dt.timedelta(seconds=sleep_s + awake)
        sleeps.append({
            "calendarDate": day.isoformat(),
            "sleepTimeSeconds": sleep_s,
            "napTimeSeconds": 0,
            "deepSleepSeconds": deep,
            "lightSleepSeconds": light,
            "remSleepSeconds": rem,
            "awakeSleepSeconds": awake,
            "sleepStartTimestampLocal": _epoch_ms(bedtime),
            "sleepEndTimestampLocal": _epoch_ms(wake),
            "avgHeartRate": round(rhr + 3 + rng.gauss(0, 1), 1),
            "averageRespirationValue": round(14 + rng.gauss(0, 0.6), 1),
            "averageSpO2Value": round(95.5 + rng.gauss(0, 0.8), 1),
            "lowestSpO2Value": int(90 + rng.gauss(0, 1.5)),
            "avgSleepStress": round(15 + 10 * fatigue + rng.gauss(0, 3), 1),
            "awakeCount": rng.randint(0, 3),
            "sleepScoreFeedback": "POSITIVE_LONG_AND_DEEP" if score >= 80 else "NONE",
            "sleepScores": {
                "overall": {"value": score, "qualifierKey": qualifier},
                "deepPercentage": {"value": round(deep / sleep_s * 100), "qualifierKey": "GOOD"},
                "remPercentage": {"value": round(rem / sleep_s * 100), "qualifierKey": "GOOD"},
            },
        })

        weekly_hrv = statistics_mean([h["lastNightAvg"] for h in hrvs[-6:]] + [hrv])
        hrvs.append({
            "calendarDate": day.isoformat(),
            "lastNightAvg": int(hrv),
            "weeklyAvg": int(weekly_hrv),
            "lastNight5MinHigh": int(hrv * 1.35),
            "baseline": {
                "lowUpper": int(profile.hrv * 0.78),
                "balancedLow": int(profile.hrv * 0.85),
                "balancedUpper": int(profile.hrv * 1.12),
            },
            "status": "BALANCED" if weekly_hrv >= profile.hrv * 0.85 else "UNBALANCED",
        })

        # Workouts from the template week, with some skipped and some extra
        day_load = 0.0
        moderate = int(max(0, rng.gauss(18, 10)))
        vigorous = 0
        for weekday, type_key, minutes, km in profile.week:
            if weekday != day.weekday() or rng.random() < 0.12 or illness:
                continue
            scale = rng.uniform(0.85, 1.15)
            km = round(km * scale * (1 + 0.04 * fitness_trend), 2)
            duration = minutes * scale * 60
            avg_hr = 128 + 22 * rng.random() + (8 if "running" in type_key else 0)
            load = duration / 60 * (avg_hr - 90) / 14
            day_load += load
            vigorous += int(duration / 120) if type_key != "walking" else 0
            moderate += int(duration / 150)
            zones = [0.08, 0.27, 0.38, 0.2, 0.07]
            if type_key in ("walking", "strength_training"):
                zones = [0.45, 0.35, 0.15, 0.05, 0.0]
            start_time = dt.datetime.combine(day, dt.time(7 if not weekend else 9, 15))
            next_id += 1
            distance = km * 1000
            activities.append({
                "activityId": next_id,
                "activityName": {
                    "running": "Morning Run", "road_biking": "Road Ride", "walking": "Walk",
                    "strength_training": "Strength",
                }.get(type_key, "Workout"),
                "startTimeLocal": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "activityType": {"typeKey": type_key},
                "distance": distance,
                "duration": duration,
                "movingDuration": duration * 0.96,
                "elevationGain": km * rng.uniform(4, 12),
                "averageSpeed": distance / duration if distance else None,
                "maxSpeed": distance / duration * 1.4 if distance else None,
                "averageHR": round(avg_hr),
                "maxHR": round(avg_hr + 25),
                "calories": round(duration / 60 * (11 if "running" in type_key else 8)),
                "aerobicTrainingEffect": round(min(5, 2 + load / 60), 1),
                "anaerobicTrainingEffect": round(rng.uniform(0.2, 2.2), 1),
                "activityTrainingLoad": round(load, 1),
                **{f"hrTimeInZone_{n + 1}": duration * z for n, z in enumerate(zones)},
                "averageRunningCadenceInStepsPerMinute": 168 + rng.gauss(0, 4)
                if "running" in type_key else None,
                "averageBikingCadenceInRevPerMinute": 86 + rng.gauss(0, 4)
                if "biking" in type_key else None,
                "steps": int(duration / 60 * 165) if "running" in type_key else None,
                "startLatitude": profile.home[0] if distance else None,
                "startLongitude": profile.home[1] if distance else None,
                "hasPolyline": bool(distance),
                "isPR": rng.random() < 0.03,
            })
            if distance and i >= DEMO_DAYS - 60:
                tracks.append((next_id, _track(profile, rng, duration, distance, avg_hr)))
        load_7d.append(day_load)

        steps = int(max(1500, profile.steps * (0.8 if weekend else 1) + rng.gauss(0, 2200)
                        - 5000 * illness))
        stress = int(max(12, 30 + 12 * fatigue + 15 * illness + rng.gauss(0, 5)
                         - (6 if weekend else 0)))
        bb_max = int(max(20, min(100, 60 + score * 0.35 + rng.gauss(0, 6) - 20 * illness)))
        bb_min = int(max(5, bb_max - 45 - day_load / 8 + rng.gauss(0, 6)))
        # Like the real API: today is only partly recorded so far.
        wear_hours = 14.0 if i == DEMO_DAYS - 1 else 24.0
        daily.append({
            "calendarDate": day.isoformat(),
            "includesWellnessData": True,
            "wellnessChronology": {"totalDurationInMillis": int(wear_hours * 3600e3)},
            "movement": {
                "steps": {"goal": 10000 if profile.seed == 7 else 8000, "value": steps,
                          "distanceInMeters": steps * 0.78},
                "floorsAscended": {"goal": 10, "value": max(0, int(rng.gauss(11, 5)))},
            },
            "calories": {"burnedResting": 1650 if profile.seed == 7 else 1420,
                         "burnedActive": int(steps * 0.04 + day_load * 4),
                         "burnedTotal": int((1650 if profile.seed == 7 else 1420)
                                            + steps * 0.04 + day_load * 4)},
            "heartRate": {"minValue": int(rhr - 4), "maxValue": int(150 + day_load / 5),
                          "restingValue": int(round(rhr))},
            "intensityMinutes": {"goal": 150, "moderate": moderate, "vigorous": vigorous},
            "stress": {
                "avgLevel": stress, "maxLevel": min(99, stress + 50),
                "qualifier": "calm" if stress < 25 else "balanced" if stress < 35 else "stressful",
                "restDurationInMillis": int(7.5 * 3600e3),
                "lowStressDurationInMillis": int(5 * 3600e3),
                "mediumStressDurationInMillis": int((1 + stress / 25) * 3600e3),
                "highStressDurationInMillis": int(max(0, stress - 25) * 2 * 60e3),
            },
            "bodyBattery": {"minValue": bb_min, "maxValue": bb_max,
                            "chargedValue": int(bb_max - bb_min + rng.gauss(0, 5)),
                            "drainedValue": int(bb_max - bb_min + rng.gauss(0, 5))},
            "hydration": {"goalInMl": 2500, "consumedInFractionalMl": max(0, rng.gauss(1900, 400))},
            "respiration": {"avgValue": int(14 + rng.gauss(0, 1)), "minValue": 9, "maxValue": 22},
            "pulseOx": {"avgValue": int(96 + rng.gauss(0, 0.8)), "minValue": 90},
        })

        weight += rng.gauss(-0.012, 0.18)
        if rng.random() < 0.45:
            weights.append({
                "summaryDate": day.isoformat(),
                "latestWeight": {
                    "weight": round(weight * 1000),  # grams, as Garmin Connect has used
                    "bmi": round(weight / (1.78 if profile.seed == 7 else 1.68) ** 2, 1),
                    "bodyFat": round(16 + (weight - profile.weight_kg) * 0.8 + rng.gauss(0, 0.4)
                                     + (6 if profile.seed == 11 else 0), 1),
                    "bodyWater": round(58 + rng.gauss(0, 0.6), 1),
                    "muscleMass": round(weight * 1000 * 0.44),
                    "boneMass": round(weight * 1000 * 0.04),
                },
            })

        if i >= DEMO_DAYS - 14:
            day_details[day] = _intraday(day, rng, rhr, bb_min, bb_max, bedtime, wake)

    fitness = [{"chronologicalAge": profile.age,
                "fitnessAge": profile.age - 4 - 3 * fitness_trend + (0 if profile.seed == 7 else 5),
                "achievableFitnessAge": profile.age - 9}]
    return {
        "daily_summaries": {"data": daily},
        "sleep": sleeps,
        "hrv": {"hrvSummaries": hrvs},
        "weight": {"dailyWeightSummaries": weights},
        "activities": activities,
        "fitness": fitness,
        "tracks": tracks,
        "day_details": day_details,
        "start": start,
    }


def statistics_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _track(profile: Profile, rng: random.Random, duration: float, distance: float,
           avg_hr: float) -> list[list[float | None]]:
    """A wobbly loop starting and ending at home."""
    lat0, lon0 = profile.home
    radius_km = distance / 1000 / (2 * math.pi)
    points = []
    n = 400
    phase = rng.uniform(0, 2 * math.pi)
    for k in range(n + 1):
        frac = k / n
        angle = phase + 2 * math.pi * frac
        wobble = 1 + 0.18 * math.sin(5 * angle + phase) + 0.07 * math.sin(13 * angle)
        dy = radius_km * wobble * (math.sin(angle) - math.sin(phase))
        dx = radius_km * wobble * (math.cos(angle) - math.cos(phase))
        lat = lat0 + dy / 111.0
        lon = lon0 + dx / (111.0 * math.cos(math.radians(lat0)))
        warmup = min(1.0, frac * 6)
        hr = avg_hr - 25 * (1 - warmup) + 8 * math.sin(frac * 9) + rng.gauss(0, 2)
        speed = distance / duration * (1 + 0.08 * math.sin(frac * 17) + rng.gauss(0, 0.03))
        points.append([round(duration * frac), round(lat, 6), round(lon, 6), round(hr),
                       round(20 + 12 * math.sin(angle * 2), 1), round(speed, 2),
                       round(distance * frac, 1)])
    return points


def _intraday(day: dt.date, rng: random.Random, rhr: float, bb_min: int, bb_max: int,
              bedtime: dt.datetime, wake: dt.datetime) -> dict:
    start = dt.datetime.combine(day, dt.time(0, 0))
    hr_values, bb_values = [], []
    bb = (bb_min + bb_max) / 2
    for minute in range(0, 24 * 60, 4):
        moment = start + dt.timedelta(minutes=minute)
        asleep = moment < wake or moment >= bedtime + dt.timedelta(days=1)
        hour = minute / 60
        exercise = 7.25 <= hour < 8.25 and rng.random() < 0.95
        hr = rhr + (2 if asleep else 18 + 8 * math.sin(hour / 3)) + (60 if exercise else 0)
        hr_values.append([_real_epoch_ms(moment), int(hr + rng.gauss(0, 3))])
        if minute % 12 == 0:
            bb = min(bb_max, bb + 1.6) if asleep else max(bb_min, bb - (3.0 if exercise else 0.55))
            bb_values.append([_real_epoch_ms(moment), int(bb), "ACTIVE"])
    return {
        "day_heart_rate": {
            "heartRateValueDescriptors": [{"index": 0, "key": "timestamp"},
                                          {"index": 1, "key": "heartrate"}],
            "heartRateValues": hr_values,
        },
        "day_body_battery": [{
            "date": day.isoformat(),
            "bodyBatteryValueDescriptorDTOList": [
                {"bodyBatteryValueDescriptorIndex": 0,
                 "bodyBatteryValueDescriptorKey": "timestamp"},
                {"bodyBatteryValueDescriptorIndex": 1,
                 "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"},
                {"bodyBatteryValueDescriptorIndex": 2,
                 "bodyBatteryValueDescriptorKey": "bodyBatteryStatus"},
            ],
            "bodyBatteryValuesArray": bb_values,
        }],
    }


def seed_demo(today: dt.date | None = None) -> list[int]:
    """(Re)create the demo profiles. Returns their person ids."""
    today = today or dt.date.today()
    remove_demo()
    ids = []
    for profile in PROFILES:
        generated = _generate(profile, today)
        with session_scope() as db:
            person = Person(name=profile.name, is_demo=True, color_slot=next_color_slot(db))
            db.add(person)
            db.flush()
            pid = person.id
            ids.append(pid)
            key = f"{generated['start'].isoformat()}..{today.isoformat()}"
            for name in ("daily_summaries", "sleep", "hrv", "weight", "activities"):
                dataset = DATASETS_BY_NAME[name]
                payload = generated[name]
                store_raw(db, pid, name, key, payload)
                upsert_rows(db, dataset.model, pid, dataset.parse(payload))
                db.add(SyncState(person_id=pid, dataset=name, synced_from=generated["start"],
                                 synced_through=today, last_run_at=utcnow(), last_status="ok"))
            store_raw(db, pid, "fitness_age", today.isoformat(), generated["fitness"])
            upsert_rows(db, FitnessAge, pid, parsers.parse_fitness_age(generated["fitness"], today))
            for activity_id, points in generated["tracks"]:
                db.add(ActivityTrack(activity_id=activity_id, points=points))
            for day, payloads in generated["day_details"].items():
                for dataset, payload in payloads.items():
                    store_raw(db, pid, dataset, day.isoformat(), payload)
    return ids


def prepare_demo_mode(today: dt.date | None = None) -> list[int]:
    """Start a public demo: refuse a data directory with real people in it, then reseed."""
    with session_scope() as db:
        real = db.scalar(select(Person.id).where(Person.is_demo.is_(False)).limit(1))
    if real is not None:
        raise RuntimeError(
            "Demo mode only runs on a data directory without real people in it, because "
            "every visitor can see everything. Point GARMATES_DATA_DIR at an empty directory."
        )
    return seed_demo(today)


def remove_demo() -> int:
    with session_scope() as db:
        demo_people = db.scalars(select(Person).where(Person.is_demo.is_(True))).all()
        for person in demo_people:
            db.delete(person)
        return len(demo_people)
