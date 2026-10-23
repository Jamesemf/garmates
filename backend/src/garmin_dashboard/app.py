"""FastAPI application: API routers, background sync scheduler and the built React app."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .api import auth, data, goals, insights, people
from .api.deps import CSRF_HEADER
from .config import Settings, get_settings
from .db import init_engine, session_scope
from .garmin.sync import sync_manager
from .models import GarminCredential

_LOGGER = logging.getLogger(__name__)
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def _scheduler(interval_minutes: int) -> None:
    """Queue a sync for everyone with a working key, now and then every interval."""
    await asyncio.sleep(5)
    while True:
        try:
            with session_scope() as db:
                ids = list(
                    db.scalars(
                        select(GarminCredential.person_id).where(
                            GarminCredential.status != "invalid"
                        )
                    )
                )
            for person_id in ids:
                sync_manager.submit(person_id)
        except Exception:
            _LOGGER.exception("Scheduler tick failed")
        await asyncio.sleep(interval_minutes * 60)


def create_app(settings: Settings | None = None, *, start_scheduler: bool = True) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    init_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if start_scheduler and settings.sync_interval_minutes > 0:
            task = asyncio.create_task(_scheduler(settings.sync_interval_minutes))
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        sync_manager.shutdown()

    app = FastAPI(title="Garmin Dashboard", lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):  # noqa: ANN001, ANN202
        if (
            request.method in _UNSAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
        response: Response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth.router)
    app.include_router(people.router)
    app.include_router(people.demo_router)
    app.include_router(data.router)
    app.include_router(goals.router)
    app.include_router(insights.router)

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            return JSONResponse(
                {"detail": "Frontend not built. Run `npm run build` in frontend/ "
                 "or use the Vite dev server on port 5173."}
            )

    return app
