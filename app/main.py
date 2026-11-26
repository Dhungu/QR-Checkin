import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import BASE_DIR, get_settings
from app.core.database import engine
from app.core.logging import configure_logging
from app.models import Base
from app.routers import attendees, check_in, events, pages, system
from app.services.errors import DomainError

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("app")

DESCRIPTION = """
QR-based event check-in with **HMAC-signed tickets**, **race-safe idempotent scanning**
(`SELECT ... FOR UPDATE` + unique constraint) and an append-only audit log.

Authorize with the `X-API-Key` header: the *admin* key for organizer endpoints,
the *staff* key (or admin key) for scanning.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="1.0.0", description=DESCRIPTION, lifespan=lifespan)

_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; media-src 'self' blob:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Ticket URLs contain the secret token: never leak them via the Referer header.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if not path.startswith(("/docs", "/redoc", "/openapi.json", "/static")):
        response.headers["Content-Security-Policy"] = _CSP
    if path.startswith(("/api", "/ticket")):
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    log.info(
        "request",
        extra={"fields": {
            "request_id": request_id, "method": request.method,
            # Never log ticket tokens that appear in the URL path.
            "path": "/ticket/<redacted>" if path.startswith("/ticket/") else path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }},
    )
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse({"status": exc.code, "detail": exc.message}, status_code=exc.status_code)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(system.router)
app.include_router(events.router)
app.include_router(attendees.router)
app.include_router(check_in.router)
app.include_router(pages.router)
