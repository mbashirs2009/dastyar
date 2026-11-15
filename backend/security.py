"""ابزارهای امنیتی مشترک: نرمال‌سازی، سیاست رمز، محدودیت نرخ، هدرها."""

from __future__ import annotations

import hashlib
import hmac
import time
import unicodedata
from typing import Any

from fastapi import HTTPException, status

# ---------------------------------------------------------------------------
# نرمال‌سازی ایمیل (ارقام فارسی/عربی، ZWNJ، فاصله)
# ---------------------------------------------------------------------------
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_INVISIBLE = set("\u200c\u200d\u200e\u200f\ufeff")


def normalize_email(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw or "")
    s = s.translate(_FA_DIGITS)
    s = "".join(ch for ch in s if ch not in _INVISIBLE)
    return s.strip().lower()


def sanitize_name(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw or "")
    s = "".join(ch for ch in s if ch.isprintable() and ch not in "<>")
    return " ".join(s.split())[:80]


def validate_avatar_url(url: str | None) -> str | None:
    if url is None:
        return None
    u = url.strip()
    if not u:
        return None
    low = u.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        raise ValueError("آواتار فقط http/https مجاز است.")
    if any(x in low for x in ("javascript:", "data:", "vbscript:")):
        raise ValueError("آواتار نامعتبر است.")
    return u[:500]


# ---------------------------------------------------------------------------
# سیاست رمز عبور
# ---------------------------------------------------------------------------
MIN_PASSWORD = 12
MAX_PASSWORD = 128

COMMON_PASSWORDS = {
    "123456", "password", "12345678", "qwerty", "123456789", "12345",
    "1234", "111111", "1234567", "dragon", "123123", "abc123",
    "password1", "iloveyou", "admin", "welcome", "monkey", "letmein",
    "000000", "test", "qwerty123", "1q2w3e4r", "admin123", "root",
    "passw0rd", "p@ssw0rd", "asdfgh", "zxcvbnm", "google", "gmail",
}


def validate_password(password: str, *, email: str = "", name: str = "") -> str:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"رمز عبور باید حداقل {MIN_PASSWORD} کاراکتر باشد.")
    if len(password) > MAX_PASSWORD:
        raise ValueError("رمز عبور بیش از حد طولانی است.")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("این رمز عبور رایج است؛ رمز قوی‌تری انتخاب کنید.")
    if email and password.lower() == email.lower():
        raise ValueError("رمز عبور نمی‌تواند برابر ایمیل باشد.")
    if name and name.lower() in password.lower():
        raise ValueError("رمز عبور نمی‌تواند شامل نام شما باشد.")
    return password


def dummy_hash() -> str:
    """هش ثابت برای هم‌زمان‌سازی زمان پاسخ ورود کاربر ناموجود."""
    return "$2b$10$CwTycUXWue0Thq9StjUM0uJ8.DWPQhX2OjB2Q0Z1jXG3lQ3YnO6mO"


# ---------------------------------------------------------------------------
# HIBP k-anonymity — fail-open
# ---------------------------------------------------------------------------
_HIBP_CACHE: dict[str, bool] = {}


def password_pwned_sync(password: str) -> bool:
    """True اگر رمز در فهرست لو‌رفته باشد. خطای شبکه = False (fail-open)."""
    if password.lower() in COMMON_PASSWORDS:
        return True
    sha = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    if sha in _HIBP_CACHE:
        return _HIBP_CACHE[sha]
    return False  # نسخه sync فقط فهرست محلی؛ HIBP در مسیر async ثبت‌نام


# ---------------------------------------------------------------------------
# محدودیت نرخ (جدول rate_limits)
# ---------------------------------------------------------------------------
def rate_limit_key(*parts: str) -> str:
    return ":".join(parts)


class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"تلاش بیش از حد. لطفاً {retry_after} ثانیه دیگر تلاش کنید.",
            headers={"Retry-After": str(retry_after)},
        )


# ---------------------------------------------------------------------------
# هدرهای امنیتی
# ---------------------------------------------------------------------------
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # CSP هفته اول Report-Only
    "Content-Security-Policy-Report-Only": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; connect-src 'self'; font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
}

NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    **SECURITY_HEADERS,
}
