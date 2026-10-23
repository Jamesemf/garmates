# Household Health – a Garmin dashboard for more than one person

A self-hosted dashboard built on Garmin's **Connect Personal API** (launched October 2026).
Everyone in the household connects their own Garmin account. You can then compare sleep,
recovery, daily activity, workouts and body metrics side by side, either as raw values
or against each person's own baseline.

- **Backend:** FastAPI + SQLite, using Garmin's official
  [`garmin-connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python)
  client.
- **Frontend:** React + TypeScript (Vite), Recharts, Leaflet/OpenStreetMap and Tailwind.
- **Runs on:** a single PC on your home network. Other devices on the network open it in
  a browser.

## What's in it

| Page | What it shows |
|---|---|
| **Overview** | Each person's last 7/14/30 days vs their own usual, with sparklines and recent workouts |
| **Weekly digest** | The week vs the previous four, highlights, goal results, and 90-day patterns |
| **Sleep & recovery** | Sleep score/duration/stages, HRV, resting HR, Body Battery, stress, bedtime and wake time |
| **Daily activity** | Steps, intensity minutes, calories, distance, floors |
| **Workouts** | Volume by sport, VO2 max, acute/chronic load, HR zones, activity list and detail with maps |
| **Body & health** | Weight, body fat, SpO2, respiration, hydration, fitness age |
| **Compare** | Head-to-head table (raw or vs own usual), and any metric indexed to each person's baseline |
| **Goals & challenges** | Personal targets with streaks, and challenges scored by total, average or improvement |
| **Day view** | One date side by side: sleep windows, intraday heart rate and Body Battery |
| **People & keys** | Garmin keys, sync status, sharing, display units, logins |

Display preferences are per viewer: distance, weight (kg/lb/stone), hydration, elevation,
week start and 12/24-hour clock. They default to each person's Garmin profile.

The **patterns** on the digest page are associations in each person's own data, such as
sleep after workout days, late nights vs HRV, and bedtime vs sleep score. They only appear
with enough nights (≥8 per group, or ≥21 paired days) and a clear effect size.

## Quick start (Windows, miniconda)

Create the environment once:

```bash
conda env create -f environment.yml
```

Then start the dashboard from the repo folder, in PowerShell or cmd:

```bash
.\start.cmd
```

`start.cmd` builds the web app on first run and starts the server through `conda run`, so
it doesn't need `conda activate`. That matters because Windows blocks PowerShell profile
scripts by default, which is why `conda activate` reports *"Run 'conda init'"* even after
you've run it.

If you'd rather have `conda activate` work in PowerShell, allow local scripts for your
user once, then open a new terminal:

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Open <http://localhost:8000>. Create the first account (it becomes the admin), then go to
**People & keys**:

1. Create a Personal API key at
   [Garmin Connect → Settings → Personal API Token](https://connect.garmin.com/app/settings/personalApiToken).
   Garmin shows the key only once.
2. Paste the key into your card and pick the lifetime you chose. The key is checked with
   Garmin, encrypted, and the first sync starts. Recent days appear within seconds and a
   year of history fills in over the next few minutes.
3. Add your partner under **Add someone** and give them a login. They sign in from their
   own device, add their own key, and choose which categories to share.

Want to look around first? **Load demo profiles** creates two synthetic people with eight
months of data.

### Reaching it from other devices

The server listens on all interfaces (port 8000). From a phone or laptop on the same
network, open `http://<this-pc's-IP>:8000`. On Windows you may need to allow
inbound TCP 8000 for *Private* networks in Windows Defender Firewall. Python will usually
prompt for this the first time it runs.

## Always-on: Raspberry Pi (Docker)

Use a **Raspberry Pi 4 or 5 (2 GB+)** running **Raspberry Pi OS Lite, 64-bit**. Give it a
fixed address with a DHCP reservation in your router. An SSD is kinder than an SD card for
a database that's written every few hours, but either works.

**1. Install Docker on the Pi** (over SSH):

```bash
curl -fsSL https://get.docker.com | sh
```
```bash
sudo usermod -aG docker $USER
```

Log out and back in so the group change applies.

**2. Copy the code across.** From this repo on your PC, make a clean archive without
`node_modules`, `data` or `.git`, then copy it to the Pi:

```bash
git archive -o garmin-dashboard.tar.gz HEAD
```
```bash
scp garmin-dashboard.tar.gz pi@raspberrypi.local:~
```

On the Pi:

```bash
mkdir -p ~/garmin-dashboard && tar xzf ~/garmin-dashboard.tar.gz -C ~/garmin-dashboard
```

**3. Configure.** In `~/garmin-dashboard`, create `.env`:

```bash
TZ=Europe/London
# Every name/address you'll use in the browser, comma-separated:
DASHBOARD_HOSTS=raspberrypi.local, 192.168.1.50
# HTTPS via Caddy (recommended) - remove this line for plain HTTP on port 8000:
COMPOSE_FILE=compose.yaml:compose.https.yaml
```

**4. Start it.** The first build takes a few minutes on a Pi 4:

```bash
docker compose up -d --build
```

Then open `https://raspberrypi.local`, or the IP you listed. Containers restart
automatically after reboots. Update later by copying a new archive across and re-running
`docker compose up -d --build`.

### HTTPS on the home network

With `compose.https.yaml`, Caddy serves the dashboard over HTTPS using its own private
certificate authority (CA). Plain HTTP only redirects, and the app's port 8000 is no longer
exposed. Browsers will warn until each device trusts that CA. You do this once per device:

1. On the device, open `http://raspberrypi.local/household-health-ca.crt` (or use the IP)
   to download the root certificate.
2. Trust it:
   - **iPhone/iPad:** Settings → *Profile Downloaded* → Install. Then Settings → General →
     About → Certificate Trust Settings → turn on full trust for it.
   - **Android:** Settings → Security → *Encryption & credentials* → Install a certificate
     → CA certificate → pick the file. Menu names vary by brand.
   - **Windows:** double-click the file → Install Certificate → Local Machine → *Trusted
     Root Certification Authorities*.
   - **macOS:** open it in Keychain Access, add it to *System*, then set it to *Always
     Trust*.
3. Reload `https://…`. The padlock should show with no warning.

The CA lives in the `caddy-data` volume. Keep it, or every device has to trust a new one.
If you'd rather not install a certificate anywhere, and you own a domain, Caddy can get a
publicly trusted certificate through a DNS challenge instead. Ask and I'll set it up.

`.local` names rely on mDNS, which some Android versions don't resolve. Use the IP address
there, and include it in `DASHBOARD_HOSTS`.

### Building on your PC instead

Building on the PC is faster, especially on a Pi with 2 GB or less. Build an ARM64 image
and copy it across:

```bash
docker buildx build --platform linux/arm64 -t garmin-dashboard:latest -o type=docker,dest=garmin-dashboard-arm64.tar .
```
```bash
docker load -i garmin-dashboard-arm64.tar
```

Run `docker load` on the Pi, then `docker compose up -d` there, without `--build`.

### Moving data from this PC to the Pi

With the containers created, copy the `data/` folder contents (including
`secrets/master.key`) into the volume:

```bash
docker compose cp ./data/. dashboard:/data
```
```bash
docker compose exec --user root dashboard chown -R dashboard:dashboard /data
```
```bash
docker compose restart
```

`docker cp` writes files as root and the app runs as an unprivileged user, so the `chown`
step is needed.

### Backing up the volume

```bash
docker run --rm -v garmin-dashboard_dashboard-data:/data -v "$PWD":/backup alpine tar czf /backup/dashboard-backup.tgz -C /data .
```

## How it works

```
Garmin Personal API ──(per-person key → 24h bearer token)──► sync engine ──► SQLite
                                                                  │   raw JSON kept verbatim
                                                                  ▼
                                    React app ◄── FastAPI (/api/…) ◄── normalised tables
```

- **Sync:** runs every 3 hours, plus a *Sync now* button. It works in chunks that respect
  Garmin's per-request date limits (daily summaries 1 year, sleep/HRV 31 days, …) and
  halves a chunk if Garmin still refuses it. It fetches recent days first, then fills in
  older history newest-first, and can resume if interrupted. The last 3 days are
  re-fetched on every run because Garmin keeps revising them.
- **Raw payloads are stored**, so if a parser needs fixing, `garmin-dashboard reparse`
  rebuilds every table without calling Garmin again.
- **On-demand detail:** activity GPS/HR streams come from each activity's original FIT file,
  and intraday heart rate and Body Battery feed the Day view. Both are fetched the first
  time you open them and cached afterwards.
- **Privacy:** each person chooses which categories (sleep & recovery, daily activity,
  workouts, body) other household members can see. The API enforces this; admins included.
  Garmin keys are encrypted at rest (Fernet; key in `data/secrets/master.key`). Passwords
  use Argon2. Sessions are HttpOnly cookies, and state-changing requests require a custom
  header (CSRF guard).

### What the Personal API doesn't provide (yet)

Training readiness, training status and Garmin's acute/chronic load aren't available. The
Workouts page approximates acute/chronic load from each activity's training load. VO2 max
comes from the value Garmin attaches to each activity.

## Commands

| Command | What it does |
|---|---|
| `garmin-dashboard serve [--host H] [--port P] [--reload]` | Run the dashboard |
| `garmin-dashboard sync [--person ID]` | Sync now, in the foreground |
| `garmin-dashboard reparse` | Rebuild tables from stored Garmin responses |
| `garmin-dashboard verify [--person ID]` | Data-quality report: coverage, gaps, out-of-range values, raw formats Garmin sent |
| `garmin-dashboard demo [--remove]` | Add/remove the synthetic demo profiles |
| `garmin-dashboard reset-password USERNAME` | Recover a locked-out account |
| `garmin-dashboard --data-dir PATH …` | Use a different data directory |

Settings come from environment variables or `.env` (see `.env.example`).

## Development

```bash
garmin-dashboard serve --reload
```
```bash
cd frontend && npm run dev
```

The Vite dev server (port 5173) proxies `/api` to FastAPI on port 8000.

```bash
cd backend && python -m pytest
```
```bash
cd backend && ruff check src tests
```
```bash
python scripts/extract_openapi_spec.py
```

The last command downloads Garmin's current OpenAPI spec (embedded in their docs page) to
`docs/`. Use it to check the parsers when Garmin changes the API.

### Layout

```
backend/src/garmin_dashboard/
  garmin/connector.py   per-person API access: token cache, pacing, retries, typed errors
  garmin/sync.py        chunked catch-up + backfill, raw storage, upserts, background runner
  garmin/parsers.py     Garmin JSON → table rows (forgiving of gaps and sentinel values)
  garmin/detail.py      FIT decoding and intraday day views (on demand, cached)
  analytics.py          series, roll-ups, baseline comparisons, training load
  catalog.py            every metric's label, unit, category and "better" direction
  api/                  auth, people/keys/sharing, data endpoints
  demo.py               synthetic profiles in Garmin's own JSON shapes
frontend/src/
  pages/                Overview, Sleep, Activity, Workouts, Body, Compare, Day, People
  components/charts.tsx shared chart kit (crosshair tooltips, legends, table views)
  lib/theme.tsx         validated colour palette (light + dark)
```

## Backups

Copy the whole `data/` folder while the server is stopped. You need both the database and
`secrets/master.key`; without the key, stored Garmin keys can't be decrypted and would
have to be re-entered.
