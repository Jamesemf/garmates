"""Every metric the dashboard can chart or compare, defined in one place.

``direction`` says whether a rise is good (``up``), bad (``down``) or neither (``none``);
the UI uses it to colour deltas. ``agg`` is how days roll up into weeks/months and into a
period value for comparisons: ``mean`` for levels (HRV, resting HR) and ``sum`` for
totals (steps, training load) - for ``sum`` metrics comparisons use the per-day average.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

CATEGORY_LABELS = {
    "sleep": "Sleep & recovery",
    "activity": "Daily activity",
    "workouts": "Workouts",
    "body": "Body & health",
}


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    category: str
    source: str  # table / derivation the value comes from
    column: str
    direction: str = "up"
    agg: str = "mean"
    decimals: int = 0
    scale: float = 1.0  # multiply stored value by this for display units
    description: str = ""
    # Physical quantity the UI may convert to the viewer's units (distance_km, mass_kg, volume_ml)
    quantity: str | None = None


METRICS: tuple[Metric, ...] = (
    # Sleep & recovery
    Metric("sleep_score", "Sleep score", "", "sleep", "sleep", "score",
           description="Garmin's overall sleep score (0-100)."),
    Metric("sleep_hours", "Sleep duration", "h", "sleep", "sleep", "duration_s", decimals=1,
           scale=1 / 3600),
    Metric("deep_hours", "Deep sleep", "h", "sleep", "sleep", "deep_s", decimals=1,
           scale=1 / 3600),
    Metric("rem_hours", "REM sleep", "h", "sleep", "sleep", "rem_s", decimals=1, scale=1 / 3600),
    Metric("light_hours", "Light sleep", "h", "sleep", "sleep", "light_s", decimals=1,
           scale=1 / 3600, direction="none"),
    Metric("awake_minutes", "Awake time", "min", "sleep", "sleep", "awake_s", direction="down",
           scale=1 / 60),
    Metric("hrv", "Overnight HRV", "ms", "sleep", "hrv", "last_night_avg",
           description="Average overnight heart rate variability."),
    Metric("hrv_weekly", "HRV 7-day avg", "ms", "sleep", "hrv", "weekly_avg"),
    Metric("rhr", "Resting heart rate", "bpm", "sleep", "daily", "rhr", direction="down"),
    Metric("bb_max", "Body Battery high", "", "sleep", "daily", "bb_max"),
    Metric("bb_min", "Body Battery low", "", "sleep", "daily", "bb_min"),
    Metric("bb_charged", "Body Battery charged", "", "sleep", "daily", "bb_charged"),
    Metric("stress_avg", "Average stress", "", "sleep", "daily", "stress_avg", direction="down"),
    Metric("stress_high_minutes", "High-stress time", "min", "sleep", "daily", "stress_high_min",
           direction="down"),
    # Clock times in hours: bedtime counts from the evening's midnight (00:30 bedtime = 24.5)
    # so averages across midnight work; wake time counts from the morning's (06:30 = 6.5).
    Metric("bedtime", "Bedtime", "clock", "sleep", "sleep_timing", "start_local",
           direction="none", decimals=2, description="When the main sleep started."),
    Metric("wake_time", "Wake time", "clock", "sleep", "sleep_timing", "end_local",
           direction="none", decimals=2, description="When the main sleep ended."),
    # Daily activity
    Metric("steps", "Steps", "", "activity", "daily", "steps", agg="sum"),
    Metric("step_goal", "Step goal", "", "activity", "daily", "step_goal", direction="none"),
    Metric("distance_km", "Distance on foot", "km", "activity", "daily", "distance_m",
           agg="sum", decimals=1, scale=1 / 1000, quantity="distance_km"),
    Metric("floors", "Floors climbed", "", "activity", "daily", "floors_up", agg="sum"),
    Metric("active_kcal", "Active calories", "kcal", "activity", "daily", "calories_active",
           agg="sum"),
    Metric("total_kcal", "Total calories", "kcal", "activity", "daily", "calories_total",
           agg="sum", direction="none"),
    Metric("intensity_minutes", "Intensity minutes", "min", "activity", "derived",
           "intensity_minutes", agg="sum",
           description="Moderate minutes plus vigorous minutes counted double, as Garmin does."),
    # Workouts (aggregated per day from activities)
    Metric("workouts", "Workouts", "", "workouts", "activities", "count", agg="sum"),
    Metric("workout_hours", "Workout time", "h", "workouts", "activities", "duration_s",
           agg="sum", decimals=1, scale=1 / 3600),
    Metric("workout_km", "Workout distance", "km", "workouts", "activities", "distance_m",
           agg="sum", decimals=1, scale=1 / 1000, quantity="distance_km"),
    Metric("training_load", "Training load", "", "workouts", "activities", "training_load",
           agg="sum", description="Sum of Garmin's per-activity training load."),
    Metric("vo2max", "VO2 max", "ml/kg/min", "workouts", "activities", "vo2max", decimals=1,
           description="VO2 max recorded with an activity. Garmin's Personal API currently "
                       "doesn't include it, so this stays empty until they do."),
    # Body & health
    Metric("weight", "Weight", "kg", "body", "weight", "weight_kg", direction="none",
           decimals=1, quantity="mass_kg"),
    Metric("body_fat", "Body fat", "%", "body", "weight", "body_fat_pct", direction="down",
           decimals=1),
    Metric("bmi", "BMI", "", "body", "weight", "bmi", direction="none", decimals=1),
    Metric("spo2", "Pulse Ox (avg)", "%", "body", "daily", "spo2_avg"),
    Metric("respiration", "Respiration (avg)", "brpm", "body", "daily", "resp_avg",
           direction="none"),
    Metric("hydration", "Hydration", "ml", "body", "daily", "hydration_ml", agg="sum",
           quantity="volume_ml"),
    Metric("fitness_age", "Fitness age", "yrs", "body", "fitness_age", "fitness_age",
           direction="down", decimals=1),
)

METRICS_BY_KEY = {m.key: m for m in METRICS}


def catalog_payload() -> dict:
    return {
        "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
        "metrics": [asdict(m) for m in METRICS],
    }
