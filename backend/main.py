"""نقطه‌ی ورود برنامه‌ی «دستیار» (FastAPI)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

import database
from auth import router as auth_router
from config import settings
from routers_chat import router as chat_router
from routers_conversations import router as conversations_router
from routers_profile import router as profile_router
from routers_telegram import router as telegram_auth_router, telegram_router
from schemas import HealthOut
from security import NO_STORE_HEADERS, SECURITY_HEADERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dastyar")

DESCRIPTION = """
بک‌اند اپلیکیشن چت هوش مصنوعی **دستیار**.

- احراز هویت: ایمیل/رمز، گوگل، گیت‌هاب، تلگرام (JWT + refresh چرخشی)
- گفتگوها و پیام‌ها
- پاسخ جریانی SSE
- ربات تلگرام + Mini App
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database.init_db()
    database.cleanup_rate_limits()
    polling_task = None
    if settings.has_telegram_bot:
        try:
            from telegram_bot import start_polling

            polling_task = asyncio.create_task(start_polling())
        except Exception:  # noqa: BLE001
            logger.warning("Telegram polling failed to start", exc_info=True)
    yield
    if polling_task:
        polling_task.cancel()


_docs_kwargs = (
    {} if not settings.is_prod else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)

app = FastAPI(
    title="دستیار API",
    description=DESCRIPTION,
    version="1.1.0",
    lifespan=lifespan,
    **_docs_kwargs,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # Bearer استفاده می‌شود؛ کوکی refresh فقط same-origin /auth
    allow_methods=["GET", "POST", "PATCH", "DELETE", "HEAD"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    response.headers["X-Request-Id"] = request_id
    path = request.url.path
    if path.startswith(("/auth", "/conversations", "/chat", "/profile")):
        response.headers["Cache-Control"] = "no-store"
    # مخفی کردن x-render-origin-server اگر بود
    response.headers.pop("x-render-origin-server", None)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    headers = getattr(exc, "headers", None) or {}
    headers = {**headers, "X-Request-Id": request_id}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": str(exc.status_code),
                "message": exc.detail,
                "request_id": request_id,
            }
        },
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = uuid.uuid4().hex
    logger.exception("unhandled error path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal",
                "message": "خطای داخلی سرور.",
                "request_id": request_id,
            }
        },
        headers={"X-Request-Id": request_id},
    )


app.include_router(auth_router)
app.include_router(telegram_auth_router)
app.include_router(telegram_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(profile_router)


API_PREFIXES = (
    "/auth",
    "/conversations",
    "/chat",
    "/profile",
    "/health",
    "/telegram",
    "/docs",
    "/openapi.json",
    "/redoc",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "model": "دستیار"}


@app.api_route("/", methods=["GET", "HEAD"], tags=["system"], include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "دستیار", "docs": "/docs", "health": "/health"}


# ── SPA — فقط مسیرهای غیر API ──────────────────────────────────────
_dist_candidates = [
    Path(__file__).resolve().parent.parent / "frontend" / "dist",
    Path(__file__).resolve().parent / "frontend" / "dist",
    Path("/app/frontend/dist"),
]
_DIST = next((p for p in _dist_candidates if p.is_dir()), None)

if _DIST is not None:

    @app.api_route("/{spa_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(spa_path: str) -> FileResponse:
        # مسیرهای API هرگز SPA نمی‌شوند — 404 JSON
        if spa_path.startswith(API_PREFIXES) or spa_path in ("health", "docs", "openapi.json"):
            raise HTTPException(status_code=404, detail="پیدا نشد.")
        target = (_DIST / spa_path).resolve()
        if spa_path and target.is_file() and str(target).startswith(str(_DIST)):
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port)
