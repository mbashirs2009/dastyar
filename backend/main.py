"""نقطه‌ی ورود برنامه‌ی «دستیار» (FastAPI).

اجرا:
    cd dastyar/backend
    python -m uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

import database
from auth import router as auth_router
from config import settings
from routers_chat import router as chat_router
from routers_conversations import router as conversations_router
from routers_profile import router as profile_router
from routers_telegram import router as telegram_auth_router, telegram_router
from schemas import HealthOut

DESCRIPTION = """
بک‌اند اپلیکیشن چت هوش مصنوعی **دستیار**.

- احراز هویت با ایمیل/رمز، گوگل، گیت‌هاب و تلگرام (JWT)
- گفتگوها و پیام‌ها در SQLite
- پاسخ جریانی (SSE) — پیش‌فرض Pollinations (بدون کلید) یا OpenRouter
- ربات تلگرام + Mini App
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """ساخت جدول‌های SQLite و روشن‌کردن ربات تلگرام اگر توکن باشد."""
    database.init_db()
    polling_task = None
    if settings.has_telegram_bot:
        try:
            from telegram_bot import start_polling

            polling_task = asyncio.create_task(start_polling())
        except Exception:  # noqa: BLE001
            logging.getLogger("dastyar").warning(
                "Telegram polling failed to start", exc_info=True
            )
    yield
    if polling_task:
        polling_task.cancel()


app = FastAPI(
    title="دستیار API",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── API (همیشه قبل از SPA catch-all) ─────────────────────────────
app.include_router(auth_router)
app.include_router(telegram_auth_router)
app.include_router(telegram_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(profile_router)


@app.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    """بررسی سلامت سرویس."""
    return HealthOut(status="ok", model="دستیار")


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": "دستیار",
        "docs": "/docs",
        "health": "/health",
    }


# ── SPA — فقط اگر frontend/dist بود (deploy روی Render) ──────────
_dist_candidates = [
    Path(__file__).resolve().parent.parent / "frontend" / "dist",
    Path(__file__).resolve().parent / "frontend" / "dist",
    Path("/app/frontend/dist"),
]
_DIST = next((p for p in _dist_candidates if p.is_dir()), None)

if _DIST is not None:

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa(spa_path: str) -> FileResponse:
        """فایل استاتیک یا index.html برای مسیرهای SPA."""
        target = (_DIST / spa_path).resolve()
        if spa_path and target.is_file() and str(target).startswith(str(_DIST)):
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port)
