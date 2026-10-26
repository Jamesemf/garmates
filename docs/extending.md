# Extending Garmates

Most changes follow one of the recipes below. Each lists every file you touch, so nothing gets
missed. Read [architecture.md](architecture.md) first if you haven't: the recipes assume you know
what the catalog, the parsers and `reparse` are.

Use demo data while you work (`garmates demo`, or **Load demo profiles** in the app), and run the
checks in [CONTRIBUTING.md](../CONTRIBUTING.md#checks) before opening a PR.

| I want to… | Recipe |
|---|---|
| Chart or compare a value that's already stored | [1. Add a metric](#1-add-a-metric-from-data-already-stored) |
| Use a field Garmin sends that isn't stored yet | [2. Store a new Garmin field](#2-store-a-new-garmin-field) |
| Sync a Garmin endpoint Garmates doesn't call yet | [3. Add a Garmin dataset](#3-add-a-garmin-dataset) |
| Show something new in the UI | [4. Add a chart or a page](#4-add-a-chart-or-a-page) |
| Find a new pattern for the weekly digest | [5. Add an insight](#5-add-an-insight) |
| Add a command | [6. Add a CLI command](#6-add-a-cli-command) |
| Check what Garmin changed | [7. Track Garmin API changes](#7-track-garmin-api-changes) |

## 1. Add a metric from data already stored

Some columns are synced and stored but not charted yet: for example `weight.muscle_mass_kg`,
`weight.body_water_pct`, `weight.bone_mass_kg`, `daily_summaries.hr_max` and
`daily_summaries.calories_resting`. Exposing one is a single entry in
[`catalog.py`](../backend/src/garmates/catalog.py):

```python
Metric("muscle_mass", "Muscle mass", "kg", "body", "weight", "muscle_mass_kg",
       direction="up", decimals=1, quantity="mass_kg"),
```

| Field | Meaning |
|---|---|
| `key` | Stable id used in URLs, goals and the API. Never rename it once released. |
| `label`, `unit` | What the UI shows. Use `unit="clock"` for times of day. |
| `category` | `sleep`, `activity`, `workouts` or `body`. It decides who can see the metric under each person's sharing settings. |
| `source`, `column` | Where the value lives: a key of `analytics._TABLES` (`daily`, `sleep`, `hrv`, `weight`, `fitness_age`), or one of the special sources `activities`, `sleep_timing` or `derived`. |
| `direction` | `up` if higher is better, `down` if lower is better, `none` if neither. It colours the deltas. |
| `agg` | `mean` for levels (HRV, weight), `sum` for totals (steps, training load). |
| `scale`, `decimals` | Multiply the stored value for display (seconds to hours is `1 / 3600`) and round. |
| `quantity` | `distance_km`, `mass_kg` or `volume_ml` lets the UI convert to each viewer's units. |

That's enough for the metric to appear in **Compare**, in **Goals** and in **Challenges**. To
chart it on a page as well, see [recipe 4](#4-add-a-chart-or-a-page).

A **derived** metric (computed from several columns) uses `source="derived"`, and you compute it
in the `derived` block of `analytics.load_daily`, the way `intensity_minutes` is computed.

## 2. Store a new Garmin field

Say the daily summaries payload has a field Garmates doesn't keep yet. Check its exact path and
type in Garmin's spec first (see [recipe 7](#7-track-garmin-api-changes)).

1. **Column.** Add a **nullable** column to the model in
   [`models.py`](../backend/src/garmates/models.py):

   ```python
   new_thing: Mapped[int | None] = mapped_column(Integer)
   ```

   Existing databases gain the column automatically on startup (`db._add_missing_columns`).

2. **Parser.** Map it in the matching function in
   [`garmin/parsers.py`](../backend/src/garmates/garmin/parsers.py), using the helpers there:
   - `_get(item, "a", "b")` walks nested keys safely.
   - `_int`/`_num` coerce numbers and treat negative sentinels as missing.
   - `allow_zero=False` drops zeros that mean "no data".
   - `_minutes` and `_kg` convert units.

   ```python
   "new_thing": _int(_get(item, "someSection", "someNewField"), allow_zero=False),
   ```

3. **Test.** Extend the payload in
   [`tests/test_parsers.py`](../backend/tests/test_parsers.py) and assert the new value. Include a
   missing or sentinel case.

4. **Metric.** Add a catalog entry ([recipe 1](#1-add-a-metric-from-data-already-stored)).

5. **Backfill.** Run `garmates reparse`. Every historical row is rebuilt from the stored raw
   responses, so the new field appears for the whole history without calling Garmin.

## 3. Add a Garmin dataset

Garmin's official client has endpoints Garmates doesn't sync yet, for example
`get_wellness_activity_summaries`, `get_effective_weight_goals`, `get_daily_food_logs` and the
menstrual-cycle endpoints. List them all with:

```bash
python -c "import garmin_personal_api as g; print([m for m in dir(g.GarminPersonalApiClient) if m.startswith('get_')])"
```

For an endpoint that takes a date range:

1. **Find the limits.** Look up the endpoint in the spec: the payload shape and the maximum days
   per request. If the spec doesn't say, start conservatively (31 days); `fetch_adaptive` halves
   a chunk that Garmin rejects anyway.

2. **Model.** Add a per-day table in `models.py`:

   ```python
   class WeightGoal(_PersonDay, Base):
       __tablename__ = "weight_goals"

       target_kg: Mapped[float | None] = mapped_column(Float)
   ```

   New tables are created automatically on startup.

3. **Parser.** Write `parse_weight_goals(payload) -> list[Row]` in `garmin/parsers.py`. Each row
   needs a `date` plus your columns, and it should skip items without a usable date.

4. **Register it** in `RANGE_DATASETS` in
   [`garmin/sync.py`](../backend/src/garmates/garmin/sync.py):

   ```python
   RangeDataset(
       "weight_goals",
       90,  # max days per request, from the spec
       lambda c, a, b: c.call(c.client.get_effective_weight_goals, a, b),
       parsers.parse_weight_goals,
       WeightGoal,
   ),
   ```

   Catch-up, backfill, chunking, raw storage and resuming all come with it.

5. **Reparse.** Add the model to the tuple of per-day models that `reparse_all` clears
   (same file).

6. **Expose it.** Add the table to `_TABLES` in
   [`analytics.py`](../backend/src/garmates/analytics.py) (e.g. `"weight_goal": WeightGoal`), and
   add catalog metrics with that `source`.

7. **Demo data (optional but appreciated).** Generate synthetic payloads in
   [`demo.py`](../backend/src/garmates/demo.py), so people without the right device can see the
   feature.

8. **Tests.** Write a parser test, plus a sync test with a fake client in the style of
   [`tests/test_sync.py`](../backend/tests/test_sync.py) (`FakeClient` + `FakeConnector`) if the
   endpoint has quirks.

For a "current state" endpoint without a date range, fetch it in `sync_snapshots` instead. For
something heavy that's only needed when someone looks at it, fetch it on demand in
[`garmin/detail.py`](../backend/src/garmates/garmin/detail.py).

## 4. Add a chart or a page

**A chart on an existing page.** Pages list their metric keys and render a `MetricChart` per
metric. [`pages/Body.tsx`](../frontend/src/pages/Body.tsx) is the smallest example:

```tsx
const METRICS = ['weight', 'body_fat', 'muscle_mass', /* … */]
// …
<MetricChart metric={byKey.muscle_mass} {...common} connectNulls />
```

`MetricChart` handles people, colours, units, buckets, tooltips and the table view. Use
`kind="bar"` for totals and `connectNulls` for sparse measurements such as weigh-ins.

**A new page:**

1. Create `frontend/src/pages/Thing.tsx`. Start from `Body.tsx`: `useFilters` gives you people,
   dates and bucket (kept in the URL), and `useSeries` / `useSummary` fetch the data.
2. Add a route in [`App.tsx`](../frontend/src/App.tsx).
3. Add it to `NAV` in [`components/Layout.tsx`](../frontend/src/components/Layout.tsx).

**A new endpoint for it.** Add the route to a router in
[`backend/src/garmates/api/`](../backend/src/garmates/api/). Take people via the `people_param`
dependency and filter every person's data through `visible_categories` from
[`api/deps.py`](../backend/src/garmates/api/deps.py), so sharing settings are respected. Add a
typed client function in `frontend/src/lib/api.ts` and a React Query hook in `lib/hooks.ts`.

**Styling.** Use the tokens (`text-ink`, `bg-surface`, `border-line`, …) and the shared pieces
in `components/ui.tsx` and `components/charts.tsx`. Person colours come from
[`lib/theme.tsx`](../frontend/src/lib/theme.tsx), which is checked for contrast in light and dark
mode. Don't add one-off colours.

## 5. Add an insight

Patterns live in `find_insights` in [`insights.py`](../backend/src/garmates/insights.py). There
are two shapes:

- **Before/after:** compare a metric between two groups of nights or days, e.g. after workout
  days and after rest days. Use `cohens_d` and require `MIN_GROUP` in each group and
  `MIN_EFFECT_D` effect size.
- **Correlation:** pair two daily series, e.g. bedtime and sleep score. Use `pearson` and
  require `MIN_PAIRS` days and `MIN_EFFECT_R`.

Rules that keep insights trustworthy:

- Only use metrics in the person's visible categories (`find_insights` is given them).
- Leave out partial days (`partial_days`).
- Word it as an association in *this person's* data: "after workout days you slept…", never "workouts
  improve sleep".
- Add a test in [`tests/test_insights.py`](../backend/tests/test_insights.py) with seeded data,
  including a case where the effect is too small to show.

## 6. Add a CLI command

Add a `cmd_<name>(args)` function and a subparser in
[`__main__.py`](../backend/src/garmates/__main__.py). Call `_init()` first if it needs the
database, and import heavy modules inside the function to keep start-up fast.

## 7. Track Garmin API changes

Garmin doesn't publish its OpenAPI spec as a file. It's embedded in the JavaScript of the
Swagger page. This script extracts it:

```bash
python scripts/extract_openapi_spec.py
```

It writes `docs/garmin-personal-api.openapi.json` (git-ignored). Diff it against an older copy
to see added or changed fields, then follow [recipe 2](#2-store-a-new-garmin-field) or
[recipe 3](#3-add-a-garmin-dataset). The spec isn't always right: check new fields against real
data with `garmates verify`. See [garmin-personal-api.md](garmin-personal-api.md) for the known
differences.
