# How Garmates works

```
Garmin Personal API ──(per-person key → 24h bearer token)──► sync engine ──► SQLite
                                                                  │   raw JSON kept verbatim
                                                                  ▼
                                    React app ◄── FastAPI (/api/…) ◄── normalised tables
```

The whole app is one Python process. It serves the built React app, answers the JSON API and
runs background syncs, all against a single SQLite file. There is no separate worker, queue or
database server, which is what keeps it comfortable on a Raspberry Pi.

## Sync

Code: [`garmin/sync.py`](../backend/src/garmates/garmin/sync.py) and
[`garmin/connector.py`](../backend/src/garmates/garmin/connector.py).

**Connector.** Each person has a `GarminConnector`, which wraps Garmin's official
[`garmin-connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python)
client:

- It exchanges the person's API key for a bearer token (about 24 hours) and caches it per
  person in `data/secrets/`.
- It spaces requests out (`GARMATES_REQUEST_SPACING_SECONDS`) and retries 429/5xx responses
  with backoff.
- It turns failures into typed errors: `KeyRejectedError`, `BadRequestError` and
  `RateLimitedError`.

**Range datasets.** Daily summaries, sleep, HRV, weight and activities are each a
`RangeDataset`: a name, the longest date span Garmin accepts per request, a fetch function, a
parser and a model. Each sync runs two passes per dataset:

1. **Catch-up:** from shortly before `synced_through` up to today. The last
   `GARMATES_RESYNC_RECENT_DAYS` are always re-fetched because Garmin revises them. If the watch
   hasn't uploaded for a while, the catch-up reaches back to the last day that had wellness data
   (up to 90 days), so late uploads still arrive.
2. **Backfill:** from `synced_from` backwards towards the person's history start, newest chunk
   first. Recent data shows up within seconds and older history fills in over the rest of the
   run. Progress is saved per chunk, so an interrupted sync resumes where it stopped.

If Garmin answers 400 for a chunk, the chunk is halved and retried (`fetch_adaptive`), so a
range limit Garmin tightens later doesn't stop the sync.

**Snapshots.** Profile settings, heart-rate zones and fitness age are fetched once per run.
The profile seeds each person's default display units.

**Scheduling.** `SyncManager` runs syncs on a small thread pool, at most one per person at a
time. A scheduler in `app.py` queues everyone with a working key every
`GARMATES_SYNC_INTERVAL_MINUTES`, and the *Sync now* button queues one person.

## Raw payloads and reparse

Every Garmin response is stored verbatim in `raw_payloads`, keyed by person, dataset and date
range, before it is parsed. `garmates reparse` (`reparse_all`) clears the per-day tables and
rebuilds them from those payloads without calling Garmin.

This is the safety net for Garmin's young API. When a parser turns out to be wrong (weight
arriving in grams rather than kilograms, say), fix the parser, run `reparse`, and every
historical row is corrected.

## On-demand detail

Code: [`garmin/detail.py`](../backend/src/garmates/garmin/detail.py).

Some data is too heavy to bulk-sync, so it's fetched the first time someone opens it and cached
afterwards:

- **Activity tracks:** GPS, heart rate, altitude and speed come from each activity's original FIT file,
  decoded with `fitdecode` and downsampled to at most 1,500 points. They're stored in
  `activity_tracks`.
- **Day view:** intraday heart rate and Body Battery for one date. Finished days are never
  fetched twice. Today and yesterday are refreshed after 30 minutes.

## Data model

Code: [`models.py`](../backend/src/garmates/models.py). Normalised per-day tables are keyed by
`(person_id, date)`.

| Table | Contents |
|---|---|
| `people` | Everyone in the household: login, admin flag, sharing categories, display preferences, chart colour |
| `garmin_credentials` | Encrypted API key, hint, expiry, status, Garmin display name |
| `auth_sessions` | Hashed session tokens |
| `raw_payloads` | Every Garmin response, verbatim |
| `sync_state` / `sync_runs` | Per-dataset progress (`synced_from`/`synced_through`) and a log of runs |
| `daily_summaries` | Steps, calories, heart rate, intensity minutes, stress, Body Battery, hydration, respiration, SpO2, wear time |
| `sleep` | Score, duration, stages, start and end (local time) |
| `hrv` | Last-night average and 5-minute high, weekly average, baseline bands, status |
| `weight` | Weight, BMI, body fat, body water, muscle and bone mass |
| `fitness_age` | Fitness age, chronological age, achievable fitness age |
| `activities` / `activity_tracks` | One row per activity, plus cached GPS/HR streams |
| `goals` / `challenges` | Personal targets and household challenges |

**Schema changes.** `init_engine` creates missing tables, and `_add_missing_columns` adds new
**nullable** columns to existing tables on startup. Anything more involved (renames, new
non-null columns, type changes) needs a migration step written alongside it.

## From tables to charts

- [`catalog.py`](../backend/src/garmates/catalog.py) defines every metric once: label, unit,
  category, where the value lives (`source` table and `column`), whether higher is better,
  and how days roll up into weeks (`mean` or `sum`). The frontend fetches it from
  `/api/catalog`, so a new metric appears in Compare, Goals and Challenges with no frontend
  change.
- [`analytics.py`](../backend/src/garmates/analytics.py) turns catalog metrics into series:
  - `load_daily` builds per-day values in display units.
  - `rollup` buckets them into weeks or months.
  - `summarise` compares a period against the person's own baseline.
  - `training_load_series` gives estimated acute and chronic load.
  - Partial days (today, or a day the watch was barely worn) are left out of totals and
    averages.
- [`insights.py`](../backend/src/garmates/insights.py) builds the weekly digest and the
  patterns. A pattern only shows with enough data (`MIN_GROUP` nights or `MIN_PAIRS` days) and a
  clear effect size (`MIN_EFFECT_D` / `MIN_EFFECT_R`), and it's worded as an association, never
  a cause.
- [`goals.py`](../backend/src/garmates/goals.py) scores goals (streaks, on-track status) and
  challenge leaderboards.

## Privacy model

- Each person picks which **categories** (sleep & recovery, daily activity, workouts, body) other
  people can see. `api/deps.py:visible_categories` enforces this on every data endpoint, and it
  applies to admins too.
- Admins can add people and manage the keys of people who have no login of their own, so a
  partner can be set up for them. Once someone has a login, only they manage their key and
  sharing.
- See [SECURITY.md](../SECURITY.md) for encryption, sessions, CSRF and the threat model.

## The local API

Everything the UI shows comes from a JSON API under `/api`. Interactive docs are at
`http://<host>:8000/api/docs`. Requests need a session cookie (`POST /api/auth/login`), and
anything that changes state also needs the `X-Garmates-Request: 1` header. It's a reasonable base
for your own integrations, such as a Home Assistant sensor or a weekly email. Treat it as
unstable until 1.0.

## Code layout

```
backend/src/garmates/
  __main__.py           CLI: serve, sync, reparse, verify, demo, reset-password
  app.py                FastAPI app, CSRF guard, scheduler, serves the built frontend
  config.py             settings (GARMATES_* env vars / .env)
  db.py                 SQLite engine, WAL, forward-only column migration
  models.py             SQLAlchemy tables
  security.py           Argon2, session tokens, Fernet encryption of keys
  catalog.py            every metric's label, unit, category and "better" direction
  analytics.py          series, roll-ups, baseline comparisons, training load
  insights.py           weekly digest and pattern-finding
  goals.py              goal progress and challenge leaderboards
  prefs.py              display units and week/clock preferences
  verify.py             data-quality report
  demo.py               synthetic profiles in Garmin's own JSON shapes
  api/                  auth, people/keys/sharing, data, goals, insights endpoints
  garmin/connector.py   per-person API access: token cache, pacing, retries, typed errors
  garmin/sync.py        chunked catch-up + backfill, raw storage, upserts, background runner
  garmin/parsers.py     Garmin JSON → table rows (forgiving of gaps and sentinel values)
  garmin/detail.py      FIT decoding and intraday day views (on demand, cached)
frontend/src/
  pages/                Overview, Digest, Sleep, Activity, Workouts, Body, Compare, Goals, Day, People
  components/charts.tsx shared chart kit (crosshair tooltips, legends, table views)
  components/MetricChart.tsx  one metric over time for the selected people
  lib/hooks.ts          React Query hooks for every endpoint, filters in the URL
  lib/theme.tsx         validated colour palette (light + dark)
  lib/units.ts          unit conversion for display preferences
```
