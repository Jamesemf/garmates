"""Database tables.

Garmin responses are kept verbatim in ``raw_payloads`` and parsed into the normalised
per-day / per-activity tables below. If a parser turns out to be wrong it can be fixed and
re-run over the stored payloads without hitting the API again (``garmates reparse``).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Data categories a person can choose to share with the rest of the household.
CATEGORIES = ("sleep", "activity", "workouts", "body")


def utcnow() -> dt.datetime:
    """Naive UTC timestamp; SQLite has no time zone support so everything is stored as UTC."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None, microsecond=0)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    # Index into the dashboard's categorical palette (light and dark steps live in the UI).
    # Assigned once at creation so a person's colour never changes when others are added.
    color_slot: Mapped[int] = mapped_column(Integer, default=0)
    username: Mapped[str | None] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_categories: Mapped[list[str]] = mapped_column(JSON, default=lambda: list(CATEGORIES))
    history_start: Mapped[dt.date | None] = mapped_column(Date)
    # Display preferences this person chose (units, week start, clock); see prefs.py.
    preferences: Mapped[dict | None] = mapped_column(JSON)
    # Same keys, derived from their Garmin profile at each sync; used where they haven't chosen.
    garmin_preferences: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    credential: Mapped[GarminCredential | None] = relationship(
        back_populates="person", cascade="all, delete-orphan", uselist=False
    )


class GarminCredential(Base):
    __tablename__ = "garmin_credentials"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(8))
    # Garmin doesn't expose the key's expiry, so the owner can record what they picked.
    key_expires_on: Mapped[dt.date | None] = mapped_column(Date)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="unverified")  # ok|invalid|unverified
    last_error: Mapped[str | None] = mapped_column(Text)
    last_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    garmin_display_name: Mapped[str | None] = mapped_column(String(120))

    person: Mapped[Person] = relationship(back_populates="credential")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)


class RawPayload(Base):
    __tablename__ = "raw_payloads"
    __table_args__ = (UniqueConstraint("person_id", "dataset", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    dataset: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    payload: Mapped[str] = mapped_column(Text)


class SyncState(Base):
    __tablename__ = "sync_state"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    synced_through: Mapped[dt.date | None] = mapped_column(Date)
    synced_from: Mapped[dt.date | None] = mapped_column(Date)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|partial|error
    message: Mapped[str | None] = mapped_column(Text)


# --- Goals & challenges -------------------------------------------------------------------


class Goal(Base):
    """A personal target on one metric, e.g. steps >= 10,000 per day or workouts >= 3 per week.

    ``target`` is in the metric's catalog units (km, kg, ml, hours…), never the viewer's.
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    metric_key: Mapped[str] = mapped_column(String(40))
    comparison: Mapped[str] = mapped_column(String(8), default="at_least")  # at_least|at_most
    target: Mapped[float] = mapped_column(Float)
    period: Mapped[str] = mapped_column(String(8), default="week")  # day|week|month
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Challenge(Base):
    """A head-to-head over a date range, scored by total, average or improvement."""

    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    metric_key: Mapped[str] = mapped_column(String(40))
    scoring: Mapped[str] = mapped_column(String(12), default="total")  # total|average|improvement
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    participant_ids: Mapped[list[int]] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


# --- Normalised metrics -------------------------------------------------------------------


class _PersonDay:
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)


class DailySummary(_PersonDay, Base):
    __tablename__ = "daily_summaries"

    # Hours of wellness data the watch recorded that day; < ~20 means a partial day
    # (today, or the last day before the watch stopped syncing).
    wear_hours: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    step_goal: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    floors_up: Mapped[int | None] = mapped_column(Integer)
    floors_goal: Mapped[int | None] = mapped_column(Integer)
    calories_total: Mapped[int | None] = mapped_column(Integer)
    calories_active: Mapped[int | None] = mapped_column(Integer)
    calories_resting: Mapped[int | None] = mapped_column(Integer)
    calories_consumed: Mapped[int | None] = mapped_column(Integer)
    rhr: Mapped[int | None] = mapped_column(Integer)
    hr_min: Mapped[int | None] = mapped_column(Integer)
    hr_max: Mapped[int | None] = mapped_column(Integer)
    intensity_moderate: Mapped[int | None] = mapped_column(Integer)
    intensity_vigorous: Mapped[int | None] = mapped_column(Integer)
    intensity_goal_weekly: Mapped[int | None] = mapped_column(Integer)
    stress_avg: Mapped[int | None] = mapped_column(Integer)
    stress_max: Mapped[int | None] = mapped_column(Integer)
    stress_qualifier: Mapped[str | None] = mapped_column(String(32))
    stress_rest_min: Mapped[float | None] = mapped_column(Float)
    stress_low_min: Mapped[float | None] = mapped_column(Float)
    stress_medium_min: Mapped[float | None] = mapped_column(Float)
    stress_high_min: Mapped[float | None] = mapped_column(Float)
    bb_min: Mapped[int | None] = mapped_column(Integer)
    bb_max: Mapped[int | None] = mapped_column(Integer)
    bb_charged: Mapped[int | None] = mapped_column(Integer)
    bb_drained: Mapped[int | None] = mapped_column(Integer)
    hydration_ml: Mapped[float | None] = mapped_column(Float)
    hydration_goal_ml: Mapped[float | None] = mapped_column(Float)
    resp_avg: Mapped[int | None] = mapped_column(Integer)
    resp_min: Mapped[int | None] = mapped_column(Integer)
    resp_max: Mapped[int | None] = mapped_column(Integer)
    spo2_avg: Mapped[int | None] = mapped_column(Integer)
    spo2_min: Mapped[int | None] = mapped_column(Integer)


class Sleep(_PersonDay, Base):
    __tablename__ = "sleep"

    score: Mapped[int | None] = mapped_column(Integer)
    score_qualifier: Mapped[str | None] = mapped_column(String(16))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    deep_s: Mapped[int | None] = mapped_column(Integer)
    light_s: Mapped[int | None] = mapped_column(Integer)
    rem_s: Mapped[int | None] = mapped_column(Integer)
    awake_s: Mapped[int | None] = mapped_column(Integer)
    nap_s: Mapped[int | None] = mapped_column(Integer)
    start_local: Mapped[dt.datetime | None] = mapped_column(DateTime)
    end_local: Mapped[dt.datetime | None] = mapped_column(DateTime)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    avg_resp: Mapped[float | None] = mapped_column(Float)
    avg_spo2: Mapped[float | None] = mapped_column(Float)
    lowest_spo2: Mapped[int | None] = mapped_column(Integer)
    avg_stress: Mapped[float | None] = mapped_column(Float)
    awake_count: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(String(64))
    component_scores: Mapped[dict | None] = mapped_column(JSON)


class Hrv(_PersonDay, Base):
    __tablename__ = "hrv"

    last_night_avg: Mapped[int | None] = mapped_column(Integer)
    last_night_5min_high: Mapped[int | None] = mapped_column(Integer)
    weekly_avg: Mapped[int | None] = mapped_column(Integer)
    baseline_low_upper: Mapped[int | None] = mapped_column(Integer)
    baseline_balanced_low: Mapped[int | None] = mapped_column(Integer)
    baseline_balanced_upper: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(16))


class Weight(_PersonDay, Base):
    __tablename__ = "weight"

    weight_kg: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    body_water_pct: Mapped[float | None] = mapped_column(Float)
    muscle_mass_kg: Mapped[float | None] = mapped_column(Float)
    bone_mass_kg: Mapped[float | None] = mapped_column(Float)


class FitnessAge(_PersonDay, Base):
    __tablename__ = "fitness_age"

    fitness_age: Mapped[float | None] = mapped_column(Float)
    chronological_age: Mapped[int | None] = mapped_column(Integer)
    achievable_fitness_age: Mapped[float | None] = mapped_column(Float)


class Activity(Base):
    __tablename__ = "activities"

    activity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    type_key: Mapped[str | None] = mapped_column(String(64))
    sport: Mapped[str] = mapped_column(String(16), default="other")
    start_local: Mapped[dt.datetime | None] = mapped_column(DateTime)
    duration_s: Mapped[float | None] = mapped_column(Float)
    moving_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    max_speed_mps: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    aerobic_te: Mapped[float | None] = mapped_column(Float)
    anaerobic_te: Mapped[float | None] = mapped_column(Float)
    training_load: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    hr_zone_s: Mapped[list | None] = mapped_column(JSON)  # seconds in zones 1-5
    avg_power: Mapped[float | None] = mapped_column(Float)
    norm_power: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lon: Mapped[float | None] = mapped_column(Float)
    has_polyline: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pr: Mapped[bool] = mapped_column(Boolean, default=False)


class ActivityTrack(Base):
    """Downsampled GPS/HR stream decoded from the activity's original FIT file."""

    __tablename__ = "activity_tracks"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.activity_id", ondelete="CASCADE"), primary_key=True
    )
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    # Columns: elapsed_s, lat, lon, heart_rate, altitude_m, speed_mps, distance_m
    points: Mapped[list | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
