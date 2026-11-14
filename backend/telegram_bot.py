"""ربات تلگرام «دستیار» — long polling با httpx، بدون کتابخانه‌ی اضافی.

نقطه‌ی ورود:
    start_polling()  -> از lifespan برنامه با asyncio.create_task صدا زده می‌شود.

رفتار:
    - اگر BOT_TOKEN خالی باشد، فوراً برمی‌گردد (برنامه بدون ربات بالا می‌آید).
    - به /start و هر پیام متنی با متن خوش‌آمد و دکمه‌ی «باز کردن دستیار» پاسخ می‌دهد.
    - خطای موقت تلگرام: ۳ ثانیه صبر و تلاش دوباره.
    - خطای قطعی (توکن نامعتبر) یا قطع دسترسی به api.telegram.org (فیلتر):
      یک هشدار فارسی و توقف کامل polling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("dastyar.telegram_bot")

API_ROOT = "https://api.telegram.org"
POLL_TIMEOUT_SECONDS = 25
# باید از timeout سرور برای long polling بیشتر باشد، وگرنه هر درخواست زودتر می‌میرد.
HTTP_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS + 15
RETRY_DELAY_SECONDS = 3
# 401/403/404 یعنی توکن نامعتبر است یا ربات حذف شده؛ تلاش دوباره بی‌فایده است.
FATAL_STATUS_CODES = frozenset({401, 403, 404})

WELCOME_TEXT = "سلام! من ربات دستیار هستم. برای باز کردن اپ، دکمه‌ی زیر را بزن."
BUTTON_TEXT = "🚀 باز کردن دستیار"
MENU_BUTTON_TEXT = "دستیار"

UNREACHABLE_WARNING = (
    "اتصال به api.telegram.org برقرار نشد (احتمالاً در ایران فیلتر است). "
    "برای فعال‌سازی ربات، سرور را با VPN/پروکسی بالا بیاورید؛ polling متوقف شد."
)

_polling_active = False
_warned_insecure_url = False


# --------------------------------------------------------------------------- #
# خطاهای لایه‌ی انتقال
# --------------------------------------------------------------------------- #
class _TelegramError(Exception):
    """خطای پایه‌ی تماس با Bot API."""


class _TelegramUnreachable(_TelegramError):
    """اتصال برقرار نشد — نشانه‌ی فیلتر بودن یا قطعی شبکه."""


class _TelegramFatal(_TelegramError):
    """توکن نامعتبر/ربات حذف‌شده؛ polling باید متوقف شود."""


class _TelegramRetryable(_TelegramError):
    """خطای موقت (۵xx، 429، timeout خواندن)؛ تلاش دوباره لازم است."""


# --------------------------------------------------------------------------- #
# کمک‌کننده‌های عمومی
# --------------------------------------------------------------------------- #
def _bot_token() -> str:
    return (settings.telegram_bot_token or "").strip()


def _api_url(method: str) -> str:
    return f"{API_ROOT}/bot{_bot_token()}/{method}"


def _describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".strip()


def _short(response: httpx.Response) -> str:
    return response.text[:200].replace("\n", " ").strip()


def _webapp_url() -> str | None:
    """آدرس https معتبر برای Web App؛ تلگرام آدرس غیر https را رد می‌کند."""
    global _warned_insecure_url

    url = (settings.telegram_webapp_url or "").strip()
    if not url:
        return None
    if not url.startswith("https://"):
        if not _warned_insecure_url:
            _warned_insecure_url = True
            logger.warning(
                "TELEGRAM_WEBAPP_URL باید https باشد؛ دکمه‌ی «باز کردن دستیار» "
                "ارسال نمی‌شود (مقدار فعلی: %s)",
                url,
            )
        return None
    return url


def _welcome_markup() -> dict[str, Any] | None:
    """reply_markup با یک دکمه‌ی web_app؛ None یعنی دکمه ساخته نشود."""
    url = _webapp_url()
    if url is None:
        return None
    return {"inline_keyboard": [[{"text": BUTTON_TEXT, "web_app": {"url": url}}]]}


# --------------------------------------------------------------------------- #
# تماس با Bot API
# --------------------------------------------------------------------------- #
async def _call(
    client: httpx.AsyncClient,
    method: str,
    payload: dict[str, Any],
) -> Any:
    """یک متد Bot API را صدا می‌زند و مقدار result را برمی‌گرداند."""
    try:
        response = await client.post(_api_url(method), json=payload)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise _TelegramUnreachable(_describe(exc)) from exc
    except httpx.HTTPError as exc:
        # timeout خواندن یا خطای پروتکل: خود درخواست سالم بود، دوباره تلاش می‌کنیم.
        raise _TelegramRetryable(_describe(exc)) from exc

    if response.status_code in FATAL_STATUS_CODES:
        raise _TelegramFatal(f"{method}: {response.status_code} {_short(response)}")
    if response.status_code >= 400:
        raise _TelegramRetryable(f"{method}: {response.status_code} {_short(response)}")

    try:
        body = response.json()
    except ValueError as exc:
        raise _TelegramRetryable(f"{method}: پاسخ تلگرام JSON نبود") from exc

    if not isinstance(body, dict) or not body.get("ok"):
        description = body.get("description") if isinstance(body, dict) else None
        raise _TelegramRetryable(f"{method}: {description or 'ok=false'}")
    return body.get("result")


async def _get_updates(
    client: httpx.AsyncClient,
    offset: int | None,
) -> list[dict[str, Any]]:
    """getUpdates با long polling؛ فقط پیام‌های ساده را می‌خواهیم."""
    payload: dict[str, Any] = {
        "timeout": POLL_TIMEOUT_SECONDS,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        payload["offset"] = offset

    result = await _call(client, "getUpdates", payload)
    return result if isinstance(result, list) else []


async def _set_menu_button(client: httpx.AsyncClient) -> None:
    """دکمه‌ی منوی چت را روی Web App تنظیم می‌کند؛ خطا مانع polling نمی‌شود."""
    url = _webapp_url()
    if url is None:
        return

    payload = {
        "menu_button": {
            "type": "web_app",
            "text": MENU_BUTTON_TEXT,
            "web_app": {"url": url},
        }
    }
    try:
        await _call(client, "setChatMenuButton", payload)
    except (_TelegramFatal, _TelegramRetryable) as exc:
        logger.warning("تنظیم دکمه‌ی منوی ربات ناموفق بود: %s", exc)


async def _handle_update(client: httpx.AsyncClient, update: dict[str, Any]) -> None:
    """به هر پیام متنی (از جمله /start) با خوش‌آمد و دکمه‌ی اپ پاسخ می‌دهد."""
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return  # Mini App در چت خصوصی با ربات معنا دارد.

    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": WELCOME_TEXT,
        "link_preview_options": {"is_disabled": True},
    }
    markup = _welcome_markup()
    if markup is not None:
        payload["reply_markup"] = markup

    await _call(client, "sendMessage", payload)


def _next_offset(update: dict[str, Any], current: int | None) -> int | None:
    """آفست بعدی تا تلگرام همان به‌روزرسانی را دوباره نفرستد."""
    update_id = update.get("update_id")
    if isinstance(update_id, int):
        return update_id + 1
    return current


# --------------------------------------------------------------------------- #
# حلقه‌ی اصلی
# --------------------------------------------------------------------------- #
async def _poll_forever() -> None:
    timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            await _set_menu_button(client)
        except _TelegramUnreachable as exc:
            logger.warning("%s (%s)", UNREACHABLE_WARNING, exc)
            return

        offset: int | None = None
        while True:
            try:
                updates = await _get_updates(client, offset)
            except _TelegramUnreachable as exc:
                logger.warning("%s (%s)", UNREACHABLE_WARNING, exc)
                return
            except _TelegramFatal as exc:
                logger.error(
                    "ربات تلگرام متوقف شد؛ BOT_TOKEN را بررسی کنید: %s", exc
                )
                return
            except _TelegramRetryable as exc:
                logger.warning(
                    "دریافت به‌روزرسانی‌های تلگرام ناموفق بود: %s — تلاش دوباره پس از %s ثانیه",
                    exc,
                    RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue

            for update in updates:
                if not isinstance(update, dict):
                    continue
                offset = _next_offset(update, offset)
                try:
                    await _handle_update(client, update)
                except _TelegramUnreachable as exc:
                    logger.warning("%s (%s)", UNREACHABLE_WARNING, exc)
                    return
                except (_TelegramFatal, _TelegramRetryable) as exc:
                    # خطای یک پیام نباید کل polling را متوقف کند.
                    logger.warning("پاسخ به به‌روزرسانی تلگرام ناموفق بود: %s", exc)


async def start_polling() -> None:
    """ربات را در حالت long polling اجرا می‌کند (از lifespan صدا زده می‌شود)."""
    global _polling_active

    if not _bot_token():
        logger.info("BOT_TOKEN تنظیم نشده است؛ ربات تلگرام اجرا نمی‌شود.")
        return
    if _polling_active:
        logger.info("polling تلگرام از قبل در حال اجراست.")
        return

    _polling_active = True
    logger.info("polling ربات تلگرام شروع شد.")
    try:
        await _poll_forever()
    except asyncio.CancelledError:
        logger.info("polling ربات تلگرام متوقف شد.")
        raise
    except Exception:  # noqa: BLE001 - نباید تسک بدون لاگ بمیرد
        logger.exception("polling ربات تلگرام با خطای پیش‌بینی‌نشده متوقف شد.")
    finally:
        _polling_active = False
