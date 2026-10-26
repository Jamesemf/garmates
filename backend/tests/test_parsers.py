import datetime as dt

from garmates.garmin import parsers


def test_daily_summary_maps_nested_fields_and_drops_sentinels():
    payload = {
        "data": [
            {
                "calendarDate": "2026-10-20",
                "movement": {"steps": {"goal": 10000, "value": 12345, "distanceInMeters": 9100.5},
                             "floorsAscended": {"goal": 10, "value": 7}},
                "calories": {"burnedResting": 1600, "burnedActive": 650, "burnedTotal": 2250},
                "heartRate": {"minValue": 44, "maxValue": 171, "restingValue": 50},
                "intensityMinutes": {"goal": 150, "moderate": 20, "vigorous": 15},
                "stress": {"avgLevel": -1, "maxLevel": 88, "qualifier": "balanced",
                           "highStressDurationInMillis": 1_800_000},
                "bodyBattery": {"minValue": 18, "maxValue": 92, "chargedValue": 70,
                                "drainedValue": 74},
                "hydration": {"goalInMl": 2500, "consumedInFractionalMl": 1800.0},
                "pulseOx": {"avgValue": 96, "minValue": 89},
            }
        ]
    }
    (row,) = parsers.parse_daily_summaries(payload)
    assert row["date"] == dt.date(2026, 10, 20)
    assert row["steps"] == 12345 and row["step_goal"] == 10000
    assert row["rhr"] == 50
    assert row["stress_avg"] is None  # -1 means "not enough data"
    assert row["stress_high_min"] == 30.0
    assert row["bb_max"] == 92
    assert row["hydration_goal_ml"] == 2500
    assert row["resp_avg"] is None  # respiration object missing entirely


def test_daily_summary_tolerates_garbage():
    assert parsers.parse_daily_summaries(None) == []
    assert parsers.parse_daily_summaries({"data": [{"calendarDate": None}, "junk"]}) == []


def test_sleep_reads_overall_score_and_epoch_timestamps():
    start = int(dt.datetime(2026, 10, 19, 22, 30, tzinfo=dt.UTC).timestamp() * 1000)
    payload = [
        {
            "calendarDate": "2026-10-20",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 900,
            "sleepStartTimestampLocal": start,
            "sleepScores": {"overall": {"value": 84, "qualifierKey": "GOOD"},
                            "remPercentage": {"value": 27}},
        },
        {"calendarDate": "2026-10-21"},  # placeholder night without data
    ]
    (row,) = parsers.parse_sleep_summaries(payload)
    assert row["score"] == 84 and row["score_qualifier"] == "GOOD"
    assert row["start_local"] == dt.datetime(2026, 10, 19, 22, 30)
    assert row["component_scores"] == {"overall": 84, "remPercentage": 27}


def test_hrv_summaries():
    payload = {"hrvSummaries": [
        {"calendarDate": "2026-10-20", "lastNightAvg": 61, "weeklyAvg": 58,
         "baseline": {"lowUpper": 45, "balancedLow": 50, "balancedUpper": 70},
         "status": "BALANCED"},
        {"calendarDate": "2026-10-21", "status": "NONE"},
    ]}
    rows = parsers.parse_hrv_summaries(payload)
    assert len(rows) == 1
    assert rows[0]["baseline_balanced_low"] == 50


def test_weight_converts_grams_to_kg_but_keeps_kg():
    payload = {"dailyWeightSummaries": [
        {"summaryDate": "2026-10-20", "latestWeight": {"weight": 72350.0, "bodyFat": 17.1,
                                                       "muscleMass": 31800}},
        {"summaryDate": "2026-10-21", "allWeightMetrics": [{"weight": 72.1}]},
    ]}
    first, second = parsers.parse_weight_range(payload)
    assert first["weight_kg"] == 72.35 and first["muscle_mass_kg"] == 31.8
    assert second["weight_kg"] == 72.1


def test_activities():
    payload = [{
        "activityId": 123, "activityName": "Lunch Run", "startTimeLocal": "2026-10-20 12:05:00",
        "activityType": {"typeKey": "trail_running"}, "distance": 10012.0, "duration": 3010.0,
        "averageHR": 151.0, "activityTrainingLoad": 140.2, "vO2MaxValue": 52.0,
        "hrTimeInZone_1": 60.0, "hrTimeInZone_3": 1800.0, "startLatitude": 51.5,
        "startLongitude": -0.12,
    }]
    (row,) = parsers.parse_activities(payload)
    assert row["sport"] == "run"
    assert row["date"] == dt.date(2026, 10, 20)
    assert row["hr_zone_s"] == [60.0, None, 1800.0, None, None]
    assert row["start_lon"] == -0.12  # negative coordinates are not sentinels


def test_classify_sport():
    assert parsers.classify_sport("road_biking") == "ride"
    assert parsers.classify_sport("lap_swimming") == "swim"
    assert parsers.classify_sport("hiking") == "walk"
    assert parsers.classify_sport("strength_training") == "strength"
    assert parsers.classify_sport("badminton") == "team"
    assert parsers.classify_sport("table_tennis") == "team"
    assert parsers.classify_sport("basketball") == "team"
    assert parsers.classify_sport("golf") == "other"
    assert parsers.classify_sport(None) == "other"


def test_intraday_series_follow_descriptors():
    hr = {"heartRateValueDescriptors": [{"index": 0, "key": "timestamp"},
                                        {"index": 1, "key": "heartrate"}],
          "heartRateValues": [[1000, 55], [2000, None], [3000, 60]]}
    assert parsers.parse_heart_rate_series(hr) == [[1000, 55], [3000, 60]]
    bb = [{"bodyBatteryValueDescriptorDTOList": [
        {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"},
        {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "timestamp"}],
        "bodyBatteryValuesArray": [[80, 1000], [79, 2000]]}]
    assert parsers.parse_body_battery_series(bb) == [[1000, 80], [2000, 79]]
