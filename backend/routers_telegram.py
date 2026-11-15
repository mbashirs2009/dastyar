"""مسیرهای ورود با تلگرام (Telegram Mini App) برای «دستیار».

مسیرها:
    POST /auth/telegram/verify  -> اعتبارسنجی initData و صدور JWT
    GET  /auth/telegram/status  -> آیا ربات پیکربندی شده است؟
    GET  /telegram/health       -> وضعیت ربات برای مانیتورینگ

اعتبارسنجی initData (طبق مستندات تلگرام):
    secret_key        = HMAC-SHA256(key=b"WebAppData", msg=bot_token)
    data_check_string = "k=v" برای همه‌ی فیلدها (به‌جز hash)، مرتب‌شده و جداشده با \\n
    hash              = HMAC-SHA256(key=secret_key, msg=data_check_string)

کاربر تلگرام مثل کاربر OAuth ذخیره می‌شود: provider="telegram" و
provider_id=<شناسه‌ی عددی تلگرام> تا ورودهای بعدی به همان حساب برسند.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

import database as db
from auth import issue_session
from config import settings
from schemas import AuthResponse, UserOut

logger = logging.getLogger("dastyar.telegram")

router = APIRouter(prefix="/auth/telegram", tags=["telegram"])
# main.py این دو نام را import می‌کند: router (احراز هویت) و telegram_router (وضعیت ربات).
telegram_router = APIRouter(prefix="/telegram", tags=["telegram"])

TELEGRAM_PROVIDER = "telegram"
WEBAPP_DATA_KEY = b"WebAppData"

NOT_CONFIGURED = "ربات تلگرام پیکربندی نشده. BOT_TOKEN را در .env بگذار."
INVALID_SIGNATURE = "امضای تلگرام معتبر نیست."
MISSING_USER = "اطلاعات کاربر در initData تلگرام پیدا نشد."


# auth.py این کمک‌کننده را دارد؛ اگر روزی حذف/تغییر نام دهد، نسخه‌ی محلی
# روی توابع database جایگزین می‌شود تا این مسیر از کار نیفتد.
_oauth_user_upsert: Any
try:  # noqa: SIM105 - ImportError تنها حالت قابل انتظار است
    from auth import _upsert_oauth_user as _oauth_user_upsert
except ImportError:  # pragma: no cover - فقط برای سازگاری با نسخه‌های قدیمی‌تر
    _oauth_user_upsert = None


# --------------------------------------------------------------------------- #
# مدل‌های ورودی/خروجی
# --------------------------------------------------------------------------- #
class TelegramVerifyIn(BaseModel):
    """بدنه‌ی درخواست: مقدار خام Telegram.WebApp.initData."""

    init_data: str = Field(min_length=1, max_length=16_384)


class TelegramStatusOut(BaseModel):
    telegram: bool


class TelegramHealthOut(BaseModel):
    ok: bool = True
    bot: bool
    webapp_url: str | None = None


# --------------------------------------------------------------------------- #
# اعتبارسنجی initData
# --------------------------------------------------------------------------- #
def _bot_token() -> str:
    return (settings.telegram_bot_token or "").strip()


def _ensure_bot_configured() -> str:
    """توکن ربات یا خطای ۵۰۱ با پیام فارسی راهنما."""
    token = _bot_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=NOT_CONFIGURED,
        )
    return token


def _parse_fields(init_data: str) -> dict[str, str]:
    """initData را به دیکشنری فیلدها تبدیل می‌کند (مقادیر percent-decoded)."""
    return dict(parse_qsl(init_data, keep_blank_values=True))


def _data_check_string(fields: dict[str, str], *, exclude: set[str]) -> str:
    """رشته‌ی امضا: فیلدهای مرتب‌شده به‌صورت k=v، جداشده با newline."""
    return "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items()) if key not in exclude
    )


def _matches_hash(
    fields: dict[str, str],
    received_hash: str,
    token: str,
    *,
    exclude_extra: frozenset[str] = frozenset(),
) -> bool:
    """مقایسه‌ی ثابت‌زمان امضای محاسبه‌شده با hash ارسالی."""
    secret_key = hmac.new(WEBAPP_DATA_KEY, token.encode("utf-8"), hashlib.sha256).digest()
    message = _data_check_string(fields, exclude={"hash", *exclude_extra})
    calculated = hmac.new(secret_key, message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash)


def _validate_init_data(init_data: str) -> dict[str, str]:
    """فیلدهای initData را پس از تأیید امضا برمی‌گرداند؛ وگرنه ۴۰۱."""
    token = _ensure_bot_configured()
    fields = _parse_fields(init_data)

    received_hash = fields.get("hash", "")
    if not received_hash:
        logger.info("Telegram initData without hash")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_SIGNATURE,
        )

    if _matches_hash(fields, received_hash, token):
        return fields

    # کلاینت‌های جدید فیلد signature را هم می‌فرستند و تلگرام آن را جدای از hash
    # امضا می‌کند؛ اگر تلگرام آن را در data-check-string نیاورده باشد، با حذف
    # signature هم بررسی می‌کنیم. این فیلد در ادامه‌ی کار خوانده نمی‌شود، پس
    # پذیرش این حالت سطح امنیتی را پایین نمی‌آورد.
    if "signature" in fields and _matches_hash(
        fields, received_hash, token, exclude_extra=frozenset({"signature"})
    ):
        return fields

    logger.warning("Telegram initData hash mismatch")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_SIGNATURE,
    )


def _parse_telegram_user(fields: dict[str, str]) -> dict[str, Any]:
    """فیلد user (رشته‌ی JSON) را به دیکشنری تبدیل می‌کند."""
    raw = fields.get("user")
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MISSING_USER)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.info("Telegram initData user field is not JSON")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=MISSING_USER
        ) from None

    if not isinstance(data, dict) or not data.get("id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MISSING_USER)
    return data


# --------------------------------------------------------------------------- #
# ساخت/اتصال کاربر
# --------------------------------------------------------------------------- #
def _upsert_telegram_user(
    *,
    provider_id: str,
    email: str,
    name: str,
    avatar_url: str | None,
) -> dict[str, Any]:
    """کاربر تلگرام را می‌سازد یا به حساب موجود با همان ایمیل متصل می‌کند."""
    if _oauth_user_upsert is not None:
        return _oauth_user_upsert(
            provider=TELEGRAM_PROVIDER,
            provider_id=provider_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
        )

    # نسخه‌ی جایگزین: همان منطق auth._upsert_oauth_user با توابع database.
    email = email.strip().lower()
    existing = db.get_user_by_oauth(TELEGRAM_PROVIDER, provider_id)
    if existing is not None:
        if avatar_url and not existing.get("avatar_url"):
            return db.update_user(existing["id"], avatar_url=avatar_url) or existing
        return existing

    by_email = db.get_user_by_email(email)
    if by_email is not None:
        return db.update_user(
            by_email["id"],
            provider=TELEGRAM_PROVIDER,
            provider_id=provider_id,
            avatar_url=by_email.get("avatar_url") or avatar_url,
            name=by_email.get("name") or name,
        ) or by_email

    return db.create_user(
        email=email,
        name=name,
        provider=TELEGRAM_PROVIDER,
        provider_id=provider_id,
        avatar_url=avatar_url,
    )


# --------------------------------------------------------------------------- #
# مسیرها
# --------------------------------------------------------------------------- #
@router.post("/verify", response_model=AuthResponse)
def verify_telegram(payload: TelegramVerifyIn, request: Request, response: Response) -> AuthResponse:
    """initData مینی‌اپ را تأیید و برای کاربر توکن JWT «دستیار» صادر می‌کند."""
    fields = _validate_init_data(payload.init_data)
    tg_user = _parse_telegram_user(fields)

    try:
        telegram_id = int(tg_user["id"])
    except (TypeError, ValueError):
        logger.info("Telegram initData has non-numeric user id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=MISSING_USER
        ) from None

    username = str(tg_user.get("username") or "").strip()
    first_name = str(tg_user.get("first_name") or "").strip()
    last_name = str(tg_user.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()

    # username در تلگرام یکتاست و به حروف حساس نیست؛ اگر نبود، شناسه‌ی عددی.
    email = f"{username or telegram_id}@telegram.local".lower()
    display_name = full_name or username or str(telegram_id)

    user = _upsert_telegram_user(
        provider_id=str(telegram_id),
        email=email,
        name=display_name,
        avatar_url=tg_user.get("photo_url"),
    )

    logger.info("Telegram login ok for user %s", telegram_id)
    access = issue_session(
        response,
        user["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:200] or None,
    )
    return AuthResponse(access_token=access, user=UserOut.model_validate(user))


@router.get("/status", response_model=TelegramStatusOut)
def telegram_status() -> TelegramStatusOut:
    """فرانت‌اند با این مسیر دکمه‌ی «ورود با تلگرام» را فعال/غیرفعال می‌کند."""
    return TelegramStatusOut(telegram=bool(_bot_token()))


@telegram_router.get("/health", response_model=TelegramHealthOut)
def telegram_health() -> TelegramHealthOut:
    """وضعیت ربات برای مانیتورینگ؛ آدرس Web App فقط وقتی ربات فعال است لو می‌رود."""
    configured = bool(_bot_token())
    return TelegramHealthOut(
        bot=configured,
        webapp_url=(settings.telegram_webapp_url or None) if configured else None,
    )
