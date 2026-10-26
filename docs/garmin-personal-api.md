# Notes on Garmin's Personal API

Garmates uses Garmin's **Connect Personal API**, which Garmin launched in October 2026 so
people can read their own Garmin Connect data with a personal key. These notes collect what
we've learned building on it. Some of it isn't in Garmin's documentation.

## Keys and tokens

- Create a key at
  [Garmin Connect → Settings → Personal API Token](https://connect.garmin.com/app/settings/personalApiToken).
- One key gives access to one Garmin account. In a household, everyone creates their own.
- You choose a lifetime between 30 days and a year. Garmin shows the key **once**.
- The key is exchanged for a bearer token that lasts about 24 hours:
  `POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token`
  with `Authorization: ApiKey <key>`. Garmin's official Python client
  ([`garmin-connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python),
  imported as `garmin_personal_api`, Python 3.12+) handles this, and Garmates caches the token
  per person.

## What Garmates syncs

| Data | Client method | Max days per request |
|---|---|---|
| Daily summaries | `get_daily_summaries` | 365 |
| Sleep | `get_daily_sleep_summaries` | 31 |
| HRV | `get_daily_hrv_summaries` | 31 |
| Weight and body composition | `get_weight_measurements` | not stated (Garmates uses 90) |
| Activities | `search_activities` (paged) | not stated (Garmates uses 90) |
| Profile, heart-rate zones, fitness age | `get_user_profile_settings`, `get_heart_rate_zones`, `get_fitness_age` | snapshot |
| Activity GPS/HR (on demand) | `download_activity` (FIT) | per activity |
| Intraday heart rate and Body Battery (on demand) | `get_daily_heart_rate`, `get_daily_body_battery` | per day |

Other documented limits: Body Battery, hydration and sleep are 31 days per request; steps and
stress are 28.

**Not synced yet** (contributions welcome, see [extending.md](extending.md#3-add-a-garmin-dataset)):
wellness activity summaries, effective weight goals, food logs, menstrual cycle data, and the
intraday SpO2, steps, stress and hydration endpoints.

## What the API doesn't provide

Checked on real accounts in October 2026:

- **Training readiness and training status** aren't available.
- **Garmin's acute/chronic load** isn't available. Garmates estimates it from each activity's
  `activityTrainingLoad`, which *is* present.
- **VO2 max** is in the spec but has been missing from every activity. Garmates keeps the
  metric, so it will fill in if Garmin starts sending it.
- **Fitness age** components are limited to vigorous days, vigorous minutes, resting heart
  rate and BMI.

## Where real data differs from the spec

These are all handled in [`garmin/parsers.py`](../backend/src/garmates/garmin/parsers.py), and
each has a test:

- **Weight arrives in grams**, although the spec says kilograms. The parser converts anything
  implausibly large.
- **Sleep `*TimestampLocal` values are epoch milliseconds** that encode local wall-clock time as
  if it were UTC.
- **Activity-only days.** Daily summaries include days where the watch wasn't worn but an
  activity was recorded, marked `includesWellnessData: false`. They carry just that activity's
  calories and are skipped, or they'd drag averages down.
- **Partial days.** `wellnessChronology.totalDurationInMillis` gives the hours the watch actually
  recorded. Days under about 20 hours (today, or the last day before the watch stopped syncing)
  are left out of totals and averages.
- **Missing days.** Days after the watch's last upload simply don't appear. When the watch
  catches up, the next sync reaches back for them.
- **Sentinels.** `-1` and `-2` mean "no data" in several fields, such as average stress. They're
  stored as missing.
- **Recent days change.** Garmin revises the last few days (late uploads, sleep re-scoring), so
  they're re-fetched on every sync.

Found another one? Run `garmates verify`, which prints coverage, gaps, out-of-range values and
the raw formats Garmin sent, and
[open a Garmin data issue](https://github.com/Jamesemf/garmates/issues/new?template=garmin_data.yml).

## The spec

Garmin doesn't offer the OpenAPI spec as a download. It's embedded as a JSON string in the
JavaScript bundle of the
[Swagger docs page](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/), and
the bundle's name changes whenever Garmin redeploys. `python scripts/extract_openapi_spec.py`
finds the bundle and writes the spec to `docs/garmin-personal-api.openapi.json`.
