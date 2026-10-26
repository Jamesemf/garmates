# Changelog

All notable changes to Garmates are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-26

### Added

- **Demo mode** (`GARMATES_DEMO_MODE=true`) for hosting a public, read-only showcase:
  - Visitors see two synthetic profiles without signing in.
  - Every change is refused.
  - The data is regenerated daily.
  - It refuses to start on a data directory that contains real people.
- An animated tour at the top of the README.

## [0.1.0] - 2026-10-26

First public release.

### Added

- **Household dashboard on Garmin's official Personal API.** Each person connects their own
  Garmin account with their own Personal API key. Nobody shares a password, and nothing is
  scraped.
- **Overview:** each person's last 7, 14 or 30 days against their own usual, with sparklines and
  recent workouts.
- **Weekly digest:** the week against the previous four, highlights, goal results, and patterns in
  each person's own data over the last 90 days (for example sleep after workout days, or bedtime
  against sleep score). Patterns only appear with enough nights and a clear effect size.
- **Sleep & recovery:** sleep score, duration and stages, overnight HRV, resting heart rate, Body
  Battery, stress, and bedtime and wake time.
- **Daily activity:** steps, intensity minutes, calories, distance and floors.
- **Workouts:** volume by sport, heart-rate zones, estimated acute and chronic load from each
  activity's training load, and an activity list with detail pages, GPS maps and heart-rate
  streams from the original FIT files.
- **Body & health:** weight, body fat, BMI, Pulse Ox, respiration, hydration and fitness age.
- **Compare:** a head-to-head table (raw values or against each person's own usual), and any
  metric indexed to each person's baseline.
- **Goals & challenges:** personal targets with streaks, and household challenges scored by
  total, average or improvement.
- **Day view:** one date side by side, with sleep windows, intraday heart rate and Body Battery.
- **People & keys:** Garmin keys with expiry warnings, sync status, per-category sharing, logins
  for each person, and display units (km/mi, kg/lb/stone, ml/fl oz, m/ft, week start, 12/24-hour
  clock) defaulting to each person's Garmin profile.
- **Sync engine:** runs every 3 hours plus on demand. It respects Garmin's per-request date limits,
  shows recent days first and backfills a year of history, and re-fetches recent days because
  Garmin revises them. Raw responses are stored, so `garmates reparse` rebuilds every table
  without calling Garmin again.
- **Privacy and security:** keys encrypted at rest (Fernet), Argon2 passwords, HttpOnly session
  cookies, a CSRF header guard, login rate limiting, and sharing enforced by the API.
- **Deployment:** multi-arch Docker images (amd64 and arm64) for PCs, NAS boxes and Raspberry Pi
  4/5, an optional HTTPS overlay using Caddy's private CA, and `start.cmd` / `start.sh` for
  running from a conda environment.
- **CLI:** `serve`, `sync`, `reparse`, `verify` (a data-quality report), `demo` (synthetic
  profiles) and `reset-password`.

[Unreleased]: https://github.com/Jamesemf/garmates/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Jamesemf/garmates/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Jamesemf/garmates/releases/tag/v0.1.0
