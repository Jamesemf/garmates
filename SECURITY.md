# Security policy

Garmates stores health data and the Garmin Personal API keys that unlock it, so security
reports are taken seriously.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately instead:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability**.

The report is visible only to the maintainers. You should get a reply within a week. Please
include the version (or commit), how you run it (Docker, from source, behind a proxy) and steps
to reproduce. Fixes are released as soon as they're ready and credited to you in the changelog
unless you'd rather stay anonymous.

## Supported versions

Security fixes go into the latest release only. Update with
`docker compose pull && docker compose up -d`, or `git pull` if you run from source.

## Threat model

Garmates is built to run **on a home network**, used by a handful of people who know each
other.

What it protects:

- **Garmin keys** are encrypted at rest with Fernet. The key lives in
  `data/secrets/master.key` or comes from `GARMATES_SECRET_KEY`. Keys are never sent back to the
  browser after you save them; only the last four characters are shown.
- **Passwords** are hashed with Argon2. Logins are rate-limited per client address.
- **Sessions** are random tokens in HttpOnly, SameSite=Lax cookies. Only a hash is stored in the
  database. Set `GARMATES_SECURE_COOKIES=true` when serving over HTTPS (the Caddy overlay does
  this for you).
- **CSRF:** every state-changing API request must carry the `X-Garmates-Request` header, which
  browsers won't add to cross-site form posts.
- **Sharing** is enforced by the API, not just hidden in the UI. Each person chooses which
  categories other people can see, and that applies to admins too.
- **No telemetry.** The server talks only to Garmin's Personal API. Browsers load map tiles from
  OpenStreetMap when you open a workout with GPS.

What it doesn't try to do:

- **Survive exposure to the internet.** Don't port-forward 8000 (or 80/443) on your router.
  For access away from home, use a VPN into your network instead, such as
  [Tailscale](https://tailscale.com) or [WireGuard](https://www.wireguard.com).
- **Protect against someone with access to the host.** Anyone who can read the `data/` folder or
  the Docker volume can read the database and decrypt the stored keys. Restrict access to the
  machine and keep backups somewhere private.
- **Isolate admins from the server.** An admin can't see data that isn't shared with them
  through the app, but anyone running the server can read the database directly.

## Out of scope

- Problems that need an attacker who already has shell access to the host or can read its
  `data/` folder.
- Missing hardening headers or TLS settings on plain-HTTP LAN installs. Use the HTTPS overlay.
- Weaknesses in Garmin's API or official client. Report those to Garmin.
- Denial of service against a server you've exposed to the internet against the advice above.
