# syntax=docker/dockerfile:1

# --- Frontend build: runs on the build machine's own architecture, output is plain files ---
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Runtime: small Python image for the target architecture (amd64 PC/NAS, arm64 Pi) ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GD_DATA_DIR=/data \
    GD_FRONTEND_DIST=/app/frontend/dist \
    GD_HOST=0.0.0.0 \
    GD_PORT=8000

# tzdata so TZ works: "today" for syncing and day views must be your local day, not UTC's.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
RUN pip install ./backend

COPY --from=frontend /app/frontend/dist /app/frontend/dist

RUN useradd --create-home --uid 1000 dashboard \
    && mkdir -p /data \
    && chown dashboard:dashboard /data
USER dashboard

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/auth/state', timeout=4)"

CMD ["garmin-dashboard", "serve"]
