# Configuration

Every setting is optional. Garmates reads them from environment variables or from a `.env` file
in the repo root (copy [`.env.example`](../.env.example)). With Docker, Compose passes `.env`
into the container too.

## App settings

All of these use the `GARMATES_` prefix and are defined in
[`backend/src/garmates/config.py`](../backend/src/garmates/config.py).

| Variable | Default | What it does |
|---|---|---|
| `GARMATES_DATA_DIR` | `./data` (`/data` in Docker) | Where the database, encrypted keys, token caches and FIT files live. `garmates --data-dir PATH` overrides it for one command. |
| `GARMATES_HOST` | `0.0.0.0` | Address to listen on. `0.0.0.0` lets other devices on your network connect; `127.0.0.1` keeps it to this machine. |
| `GARMATES_PORT` | `8000` | Port to listen on. |
| `GARMATES_SYNC_INTERVAL_MINUTES` | `180` | How often everyone is synced in the background. `0` means only when someone presses *Sync now*. |
| `GARMATES_DEFAULT_HISTORY_DAYS` | `365` | How far back the first sync for a new person reaches. |
| `GARMATES_RESYNC_RECENT_DAYS` | `3` | Recent days re-fetched on every sync, because Garmin keeps revising them (late uploads, sleep re-scoring). |
| `GARMATES_REQUEST_SPACING_SECONDS` | `0.4` | Pause between Garmin requests. Garmin doesn't publish a rate limit, so Garmates stays polite. |
| `GARMATES_SECRET_KEY` | *(unset)* | Fernet key that encrypts stored Garmin keys. If unset, one is generated in `data/secrets/master.key` on first run. Back that file up with the database. |
| `GARMATES_SESSION_DAYS` | `30` | How long a login lasts. |
| `GARMATES_SECURE_COOKIES` | `false` | Mark session cookies HTTPS-only. Set it only when serving over HTTPS. The Caddy overlay sets it for you. |
| `GARMATES_TRUST_PROXY` | `false` | Trust `X-Forwarded-For`/`-Proto` from a reverse proxy, so login rate limiting sees each device's address. Enable it only when the app isn't reachable directly. The Caddy overlay sets it. |
| `GARMATES_FRONTEND_DIST` | `./frontend/dist` | The built web app that FastAPI serves. |
| `GARMATES_DEMO_MODE` | `false` | Run a public, read-only demo: synthetic profiles regenerated daily, no sign-in, every change refused. It won't start on a data directory with real people in it. See [Hosting a public demo](installation.md#hosting-a-public-demo). |

To generate your own `GARMATES_SECRET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If you change the key later, stored Garmin keys can't be decrypted and have to be entered
again. Synced data isn't affected.

## Docker settings

These are read by Compose, not by the app.

| Variable | Default | What it does |
|---|---|---|
| `TZ` | `UTC` | **Set this.** Your time zone, e.g. `Europe/London` or `America/New_York`. Syncing and day views use "today" in this zone. |
| `GARMATES_VERSION` | `latest` | Image tag to run, e.g. `0.1.0` to stay on one release. |
| `COMPOSE_FILE` | `compose.yaml` | Set it to `compose.yaml:compose.https.yaml` to turn on the HTTPS overlay. On Windows, separate the files with `;` instead, or also set `COMPOSE_PATH_SEPARATOR=:`. |
| `DASHBOARD_HOSTS` | `raspberrypi.local` | HTTPS overlay only: every name or address you'll type in the browser, comma-separated. Caddy issues certificates only for these. |

## In the app

These are set per person on the **People & keys** page, not in the environment:

- **Garmin key** and its lifetime.
- **Sharing:** which categories other people can see.
- **Display units:** distance, weight (kg/lb/stone), hydration, elevation, week start, and the
  12- or 24-hour clock. They default to each person's Garmin profile.
- **Logins:** each person's own username and password. Admins can add people and reset passwords.
