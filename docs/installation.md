# Installing Garmates

Garmates runs on one machine on your home network, and everyone else opens it in a browser.
Pick whichever setup suits you:

| Setup | Good for |
|---|---|
| [Docker](#docker-any-os) | The quickest start on any OS, or an always-on PC or NAS |
| [Raspberry Pi](#raspberry-pi) | A quiet always-on box for the whole household |
| [Windows from source](#windows-from-source) | Running it on your PC without Docker |
| [macOS or Linux from source](#macos-or-linux-from-source) | Development, or no Docker |

Then see [Connecting Garmin accounts](#connecting-garmin-accounts).

## Docker (any OS)

You need [Docker](https://docs.docker.com/get-docker/) with Compose v2.

1. Get the files:

   ```bash
   git clone https://github.com/Jamesemf/garmates.git
   cd garmates
   ```

2. Set your time zone. "Today" for syncing and day views is your local day. Create `.env` next
   to `compose.yaml`:

   ```bash
   TZ=Europe/London
   ```

   Use your own [tz database name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones),
   e.g. `America/New_York`.

3. Start it:

   ```bash
   docker compose up -d
   ```

   Compose pulls the prebuilt image for your architecture (amd64 or arm64) and restarts it
   automatically after reboots.

Open `http://<this-machine's-IP>:8000`, or <http://localhost:8000> on the same machine.

**Just want a look?** You can run it with no clone and no config:

```bash
docker run -d -p 8000:8000 -v garmates-data:/data --name garmates ghcr.io/jamesemf/garmates
```

Create an account, then press **Load demo profiles** on the People & keys page.

### Updating

```bash
git pull
docker compose pull
docker compose up -d
```

To stay on one release, put `GARMATES_VERSION=0.1.0` in `.env`. To build the image from source
instead of pulling it, use `docker compose up -d --build`.

## Raspberry Pi

Use a **Raspberry Pi 4 or 5 (2 GB+)** running **Raspberry Pi OS Lite (64-bit)**.

- Give it a fixed address with a DHCP reservation in your router.
- An SSD is kinder than an SD card to a database that's written every few hours, but either
  works.

**1. Install Docker** (over SSH):

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo usermod -aG docker $USER
```

Log out and back in so the group change applies.

**2. Get Garmates:**

```bash
git clone https://github.com/Jamesemf/garmates.git ~/garmates && cd ~/garmates
```

**3. Configure.** Create `~/garmates/.env`:

```bash
TZ=Europe/London
# Every name/address you'll type in the browser, comma-separated:
DASHBOARD_HOSTS=raspberrypi.local, 192.168.1.50
# HTTPS via Caddy (recommended). Remove this line for plain HTTP on port 8000:
COMPOSE_FILE=compose.yaml:compose.https.yaml
```

**4. Start it:**

```bash
docker compose up -d
```

The prebuilt arm64 image means nothing has to compile on the Pi. Open
`https://raspberrypi.local`, or the IP you listed, and see
[HTTPS on the home network](#https-on-the-home-network) to stop the browser warning.

Update the same way as any Docker install: `git pull && docker compose pull && docker compose up -d`.

## HTTPS on the home network

With `compose.https.yaml`, [Caddy](https://caddyserver.com) serves Garmates over HTTPS using its
own private certificate authority (CA):

- Plain HTTP only redirects.
- The app's port 8000 is no longer exposed.
- Secure cookies are switched on.

Browsers will warn until each device trusts that CA. You do this once per device:

1. On the device, open `http://raspberrypi.local/garmates-ca.crt` (or use the IP) to download the
   root certificate.
2. Trust it:
   - **iPhone/iPad:** Settings → *Profile Downloaded* → Install. Then Settings → General →
     About → Certificate Trust Settings → turn on full trust for it.
   - **Android:** Settings → Security → *Encryption & credentials* → Install a certificate
     → CA certificate → pick the file. Menu names vary by brand.
   - **Windows:** double-click the file → Install Certificate → Local Machine → *Trusted
     Root Certification Authorities*.
   - **macOS:** open it in Keychain Access, add it to *System*, then set it to *Always Trust*.
3. Reload `https://…`. The padlock should show with no warning.

Things to know:

- **Keep the `caddy-data` volume.** The CA lives there. Without it, every device has to trust a
  new CA.
- **List every address in `DASHBOARD_HOSTS`.** Caddy only has certificates for the addresses
  listed there, so an unlisted IP fails the secure connection outright.
- **`.local` names need mDNS,** which some Android versions don't resolve. On those devices use
  the IP address, and include it in `DASHBOARD_HOSTS`.
- **Own a domain?** Caddy can get a publicly trusted certificate through a DNS challenge instead,
  so no device needs to trust a private CA. See Caddy's
  [DNS challenge docs](https://caddyserver.com/docs/automatic-https#dns-challenge) and adapt
  `deploy/Caddyfile`.

### Away from home

Garmates is designed for a trusted home network, so **don't port-forward it on your router**.
To use it while you're out, join your home network with a VPN such as
[Tailscale](https://tailscale.com) or [WireGuard](https://www.wireguard.com). See
[SECURITY.md](../SECURITY.md).

## Windows from source

You need [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (or Anaconda). Node is
installed into the environment, so you don't need it system-wide.

Create the environment once, from the repo folder:

```bash
conda env create -f environment.yml
```

Then start Garmates from PowerShell or cmd:

```bash
.\start.cmd
```

`start.cmd` builds the web app on the first run, then starts the server through `conda run`, so
it doesn't need `conda activate`. That matters because Windows blocks PowerShell profile scripts
by default, which is why `conda activate` can report *"Run 'conda init'"* even after you've run
it. If you'd rather have `conda activate` work in PowerShell, allow local scripts for your user
once, then open a new terminal:

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Open <http://localhost:8000>.

**Reaching it from other devices:** the server listens on all interfaces, so from a phone or
laptop on the same network open `http://<this-pc's-IP>:8000`. You may need to allow inbound
TCP 8000 for *Private* networks in Windows Defender Firewall. Python usually prompts for this the
first time it runs.

## macOS or Linux from source

You need Python 3.12+ and Node 22. **With conda,** create the environment and use the start
script:

```bash
conda env create -f environment.yml
./start.sh
```

**Without conda:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e backend
(cd frontend && npm ci && npm run build)
garmates serve
```

Open <http://localhost:8000>. Extra arguments pass through, e.g. `./start.sh --port 9000`. To
keep it running after you log out, run `garmates serve` under systemd, launchd or similar, or use
Docker instead.

## Connecting Garmin accounts

1. Open Garmates and **create the first account**. It becomes the admin.
2. Create a Personal API key at
   [Garmin Connect → Settings → Personal API Token](https://connect.garmin.com/app/settings/personalApiToken).
   You can choose a lifetime from 30 days to a year. Garmin shows the key **only once**.
3. On **People & keys**, paste the key into your card and pick the lifetime you chose. Garmates
   checks the key with Garmin, encrypts it and starts the first sync. Recent days appear within
   seconds, and a year of history fills in over the next few minutes.
4. Add your partner (or anyone else) under **Add someone** and give them a login. They sign in
   from their own device, add their own key, and choose which categories to share.

Garmates warns you before a key expires. A new key for the same Garmin account keeps everything
already synced. A key for a different account starts that person's sync from scratch.

## Backups

You need **both** the database and the encryption key. Without `secrets/master.key`, stored
Garmin keys can't be decrypted and everyone would have to enter theirs again. Your synced data
itself would survive.

**From source:** stop the server and copy the whole `data/` folder.

**Docker:** with Compose's fixed project name the volume is `garmates_dashboard-data`:

```bash
docker run --rm -v garmates_dashboard-data:/data -v "$PWD":/backup alpine tar czf /backup/garmates-backup.tgz -C /data .
```

Restore by extracting it back into the volume while the container is stopped.

## Moving from a PC to a Pi

Start Garmates on the Pi once so the volume exists. Then, from the repo folder on the Pi, with
your PC's `data/` folder copied across:

```bash
docker compose cp ./data/. dashboard:/data
```

```bash
docker compose exec --user root dashboard chown -R garmates:garmates /data
```

```bash
docker compose restart
```

`docker compose cp` writes files as root and the app runs as an unprivileged user, which is why
the `chown` step is needed. A database from a version before the rename
(`garmin-dashboard.sqlite3`) is picked up automatically.

## Hosting a public demo

Demo mode turns Garmates into a read-only showcase that's safe to put on the internet, for
example to link from a blog post. It holds only the two synthetic demo profiles:

- Visitors see the dashboard straight away, without signing in.
- Every change is refused, including setup, logins, Garmin keys, goals and settings.
- The demo data is regenerated each day, so it always runs up to today.
- It refuses to start if the data directory contains any real person. Never point it at your
  household's data.

Run it on any Docker host or container platform:

```bash
docker run -d -p 8000:8000 -e GARMATES_DEMO_MODE=true --name garmates-demo ghcr.io/jamesemf/garmates
```

Don't mount a volume, or use a fresh one: a new container generates its own data. Put it
behind your platform's HTTPS. No other settings are needed.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Can't reach the dashboard server" | The backend isn't running, or (in development) isn't on port 8000. |
| Other devices can't connect | Check the firewall on the host (TCP 8000, or 80/443 with HTTPS) and use the host's LAN IP, not `localhost`. |
| HTTPS "connection not secure" on one address | That address isn't in `DASHBOARD_HOSTS`. Add it and run `docker compose up -d`. |
| Days are a day off around midnight | `TZ` isn't set to your time zone. |
| Locked out | `garmates reset-password USERNAME` (Docker: `docker compose exec dashboard garmates reset-password USERNAME`). |
| Data looks wrong | Run `garmates verify` and [open a Garmin data issue](https://github.com/Jamesemf/garmates/issues/new?template=garmin_data.yml). |
