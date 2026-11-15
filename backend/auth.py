"""احراز هویت «دستیار»: نشست واقعی، refresh چرخشی، محدودیت نرخ، سیاست رمز.

مسیرها:
    POST /auth/register
    POST /auth/login
    POST /auth/refresh
    POST /auth/logout
    GET  /auth/me
    POST /auth/change-password
    POST /auth/forgot-password
    POST /auth/reset-password
    GET  /auth/google|github + callback
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import quote, urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

import database as db
from database import utcnow
from config import settings
from schemas import (
    AuthResponse,
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    OkOut,
    RegisterIn,
    ResetPasswordIn,
    UserOut,
)
from security import RateLimitExceeded, dummy_hash, normalize_email, validate_password

logger = logging.getLogger("dastyar.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "dastyar"
OAUTH_STATE_TTL_SECONDS = 600
ACCESS_MIN = max(settings.access_token_minutes, 5)
REFRESH_DAYS = max(settings.refresh_token_days, 1)
REFRESH_MAX_AGE = REFRESH_DAYS * 86400
LOGIN_WINDOW = 15 * 60
LOGIN_MAX_EMAIL = 5
LOGIN_MAX_IP = 10
REGISTER_WINDOW = 3600
REGISTER_MAX_IP = 5

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"

pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=10, deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")

INVALID_CREDENTIALS = "ایمیل یا رمز عبور نادرست است."
UNAUTHORIZED = "برای دسترسی باید وارد شوید."
RATE_MSG = "تلاش بیش از حد. کمی بعد دوباره تلاش کنید."
AMBIGUOUS_REGISTER = "اگر این ایمیل معتبر باشد، حساب شما فعال است. وارد شوید."


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return pwd_context.hash(_password_bytes(password))


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return pwd_context.verify(_password_bytes(password), password_hash)
    except (ValueError, TypeError):
        logger.warning("bcrypt verification failed for stored hash")
        return False


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_plus(**kwargs: int) -> tuple[datetime, str]:
    dt = datetime.now(timezone.utc) + timedelta(**kwargs)
    return dt, dt.replace(microsecond=0).isoformat()


def _jwt(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


# --------------------------------------------------------------------------- #
# توکن‌ها
# --------------------------------------------------------------------------- #
def create_access_token(user_id: int, jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "jti": jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_MIN)).timestamp()),
    }
    return _jwt(payload)


def create_refresh_token(user_id: int, jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_DAYS)).timestamp()),
    }
    return _jwt(payload)


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
        )
    except jwt.PyJWTError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload


def _make_state(provider: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": f"oauth:{provider}",
        "nonce": secrets.token_urlsafe(12),
        "exp": int((now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS)).timestamp()),
    }
    return _jwt(payload)


def _check_state(state: str | None, provider: str) -> bool:
    if not state:
        return False
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("purpose") == f"oauth:{provider}"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "dastyar_refresh",
        token,
        httponly=True,
        secure=settings.is_prod,
        samesite="lax",
        max_age=REFRESH_MAX_AGE,
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("dastyar_refresh", path="/auth")


def issue_session(response: Response, user_id: int, *, ip: str | None, user_agent: str | None) -> str:
    access_jti = secrets.token_urlsafe(16)
    refresh_jti = secrets.token_urlsafe(24)
    refresh_token = create_refresh_token(user_id, refresh_jti)
    _, expires_at = _utc_plus(days=REFRESH_DAYS)
    db.create_session(
        user_id=user_id,
        jti=access_jti,
        refresh_jti=refresh_jti,
        refresh_hash=_sha256(refresh_token),
        user_agent=(user_agent or "")[:200] or None,
        ip=ip,
        expires_at=expires_at,
    )
    access = create_access_token(user_id, access_jti)
    _set_refresh_cookie(response, refresh_token)
    return access


# --------------------------------------------------------------------------- #
# وابستگی «کاربر جاری»
# --------------------------------------------------------------------------- #
def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نشست شما منقضی شده است؛ دوباره وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    jti = payload.get("jti")
    user_id = payload.get("sub")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail=UNAUTHORIZED) from None

    session = db.get_session_by_jti(jti) if jti else None
    if session is None or session.get("revoked_at") or session.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نشست شما منقضی شده است؛ دوباره وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    db.touch_session(jti)
    user = db.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED)
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:200] or None
    return ip, ua


def _rate_or_429(key: str, max_count: int, window: int) -> None:
    if not db.rate_hit(key, max_count, window):
        raise RateLimitExceeded(retry_after=window)


# --------------------------------------------------------------------------- #
# ثبت‌نام / ورود / خروج / refresh
# --------------------------------------------------------------------------- #
@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response) -> Any:
    ip, ua = _client_meta(request)
    _rate_or_429(f"register:ip:{ip}", REGISTER_MAX_IP, REGISTER_WINDOW)

    if db.get_user_by_email(payload.email) is not None:
        # پیام مبهم — افشای وجود ایمیل ممنوع
        return {"ok": True, "message": AMBIGUOUS_REGISTER}

    user = db.create_user(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        provider="email",
    )
    db.add_audit(user["id"], "register", ip=ip, user_agent=ua)
    access = issue_session(response, user["id"], ip=ip, user_agent=ua)
    return AuthResponse(access_token=access, user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginIn, request: Request, response: Response) -> AuthResponse:
    ip, ua = _client_meta(request)
    _rate_or_429(f"login:email:{payload.email}", LOGIN_MAX_EMAIL, LOGIN_WINDOW)
    _rate_or_429(f"login:ip:{ip}", LOGIN_MAX_IP, LOGIN_WINDOW)

    user = db.get_user_by_email(payload.email)
    password_hash = db.get_user_password_hash(user["id"]) if user else dummy_hash()
    ok = verify_password(payload.password, password_hash)
    if user is None or not ok:
        db.add_audit(user["id"] if user else None, "login_failed", ip=ip, user_agent=ua)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    db.add_audit(user["id"], "login", ip=ip, user_agent=ua)
    access = issue_session(response, user["id"], ip=ip, user_agent=ua)
    return AuthResponse(access_token=access, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response) -> AuthResponse:
    token = request.cookies.get("dastyar_refresh")
    if not token:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED)
    payload = decode_token(token, expected_type="refresh")
    if payload is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="نشست منقضی شده.")
    refresh_jti = payload.get("jti")
    user_id = payload.get("sub")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail=UNAUTHORIZED) from None

    session = db.get_session_by_refresh_jti(refresh_jti) if refresh_jti else None
    if session is None or session.get("revoked_at") or session.get("user_id") != user_id:
        # استفاده مجدد از refresh باطل‌شده = ابطال همه نشست‌های کاربر
        if user_id:
            db.revoke_all_user_sessions(user_id)
            db.add_audit(user_id, "refresh_reuse", ip=_client_meta(request)[0])
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="نشست نامعتبر است. دوباره وارد شوید.")

    if session.get("expires_at") < utcnow():
        db.revoke_session(session["jti"])
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="نشست منقضی شده.")

    ip, ua = _client_meta(request)
    new_access_jti = secrets.token_urlsafe(16)
    new_refresh_jti = secrets.token_urlsafe(24)
    new_refresh = create_refresh_token(user_id, new_refresh_jti)
    db.rotate_session(
        refresh_jti,
        new_jti=new_access_jti,
        new_refresh_jti=new_refresh_jti,
        new_refresh_hash=_sha256(new_refresh),
    )
    access = create_access_token(user_id, new_access_jti)
    _set_refresh_cookie(response, new_refresh)
    return AuthResponse(access_token=access, user=UserOut.model_validate(db.get_user(user_id) or {}))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout", response_model=OkOut)
def logout(
    request: Request,
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    user: CurrentUser,
) -> OkOut:
    payload = decode_token(credentials.credentials, expected_type="access") if credentials else None
    jti = (payload or {}).get("jti")
    if jti:
        db.revoke_session(jti)
        db.add_audit(user["id"], "logout", ip=_client_meta(request)[0])
    _clear_refresh_cookie(response)
    return OkOut(ok=True)


@router.post("/change-password", response_model=OkOut)
def change_password(
    payload: ChangePasswordIn,
    request: Request,
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    user: CurrentUser,
) -> OkOut:
    password_hash = db.get_user_password_hash(user["id"])
    if not verify_password(payload.current_password, password_hash):
        raise HTTPException(status_code=401, detail="رمز فعلی نادرست است.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="رمز جدید باید با فعلی تفاوت داشته باشد.")
    db.update_user(user["id"], password_hash=hash_password(payload.new_password))
    db.revoke_all_user_sessions(user["id"], except_jti=None)
    _clear_refresh_cookie(response)
    db.add_audit(user["id"], "change_password", ip=_client_meta(request)[0])
    return OkOut(ok=True)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordIn, request: Request) -> dict[str, str]:
    ip, ua = _client_meta(request)
    _rate_or_429(f"forgot:ip:{ip}", 5, 3600)
    user = db.get_user_by_email(payload.email)
    # پاسخ همیشه یکسان — افشای وجود ایمیل ممنوع
    message = "اگر این ایمیل معتبر باشد، لینک بازیابی ارسال شد."
    if user:
        raw = secrets.token_urlsafe(32)
        _, expires = _utc_plus(minutes=45)
        db.create_password_reset(user["id"], _sha256(raw), expires)
        db.add_audit(user["id"], "forgot_password", ip=ip, user_agent=ua)
        # SMTP پیکربندی نشده؛ لینک فقط در لاگ سرور (برای ادمین)
        link = f"{settings.frontend_url}/reset-password?token={quote(raw, safe='')}"
        logger.info("password reset link for user %s: %s", user["id"], link)
    return {"ok": True, "message": message}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordIn, request: Request) -> OkOut:
    ip, ua = _client_meta(request)
    token_hash = _sha256(payload.token)
    row = db.get_valid_password_reset(token_hash)
    if not row:
        raise HTTPException(status_code=400, detail="لینک بازیابی نامعتبر یا منقضی است.")
    db.update_user(row["user_id"], password_hash=hash_password(payload.new_password))
    db.use_password_reset(token_hash)
    db.revoke_all_user_sessions(row["user_id"])
    db.add_audit(row["user_id"], "reset_password", ip=ip, user_agent=ua)
    return OkOut(ok=True)


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #
def _frontend_redirect(*, error: str | None = None) -> RedirectResponse:
    if error:
        url = f"{settings.frontend_url}/?error={quote(error or 'oauth_failed', safe='')}"
    else:
        url = settings.frontend_url
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _ensure_provider_configured(provider: str) -> None:
    if provider == "google" and not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="سرویس گوگل در دسترس نیست.",
        )
    if provider == "github" and not (settings.github_client_id and settings.github_client_secret):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="سرویس گیت‌هاب در دسترس نیست.",
        )


def _upsert_oauth_user(
    *,
    provider: str,
    provider_id: str,
    email: str,
    name: str | None,
    avatar_url: str | None,
) -> dict[str, Any]:
    email = normalize_email(email)
    display_name = (name or "").strip() or email.split("@")[0]

    existing = db.get_user_by_oauth(provider, provider_id)
    if existing is not None:
        updates: dict[str, Any] = {}
        if avatar_url and not existing.get("avatar_url"):
            updates["avatar_url"] = avatar_url
        if updates:
            return db.update_user(existing["id"], **updates) or existing
        return existing

    by_email = db.get_user_by_email(email)
    if by_email is not None:
        return db.update_user(
            by_email["id"],
            provider=provider,
            provider_id=provider_id,
            avatar_url=by_email.get("avatar_url") or avatar_url,
            name=by_email.get("name") or display_name,
        ) or by_email

    return db.create_user(
        email=email,
        name=display_name,
        provider=provider,
        provider_id=provider_id,
        avatar_url=avatar_url,
    )


def _finish_oauth(request: Request, response: Response, user: dict[str, Any]) -> RedirectResponse:
    ip, ua = _client_meta(request)
    issue_session(response, user["id"], ip=ip, user_agent=ua)
    db.add_audit(user["id"], f"login_{user.get('provider')}", ip=ip, user_agent=ua)
    return _frontend_redirect()


@router.get("/providers")
def oauth_providers() -> dict[str, bool]:
    return {
        "google": bool(settings.google_client_id and settings.google_client_secret),
        "github": bool(settings.github_client_id and settings.github_client_secret),
        "telegram": settings.has_telegram_bot,
    }


@router.get("/google")
def google_login() -> RedirectResponse:
    _ensure_provider_configured("google")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": _make_state("google"),
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=status.HTTP_302_FOUND)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    _ensure_provider_configured("google")
    if error:
        return _frontend_redirect(error="google_cancelled")
    if not code:
        return _frontend_redirect(error="google_missing_code")
    if not _check_state(state, "google"):
        return _frontend_redirect(error="invalid_state")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_response.status_code >= 400:
                logger.warning("Google token exchange failed: %s", token_response.text[:200])
                return _frontend_redirect(error="google_failed")
            access_token = token_response.json().get("access_token")
            if not access_token:
                return _frontend_redirect(error="google_failed")
            info_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_response.status_code >= 400:
                return _frontend_redirect(error="google_failed")
            info = info_response.json()
    except httpx.HTTPError as exc:
        logger.warning("Google OAuth request error: %s", exc)
        return _frontend_redirect(error="google_failed")

    email = (info.get("email") or "").strip().lower()
    if not email:
        return _frontend_redirect(error="google_no_email")
    user = _upsert_oauth_user(
        provider="google",
        provider_id=str(info.get("sub") or email),
        email=email,
        name=info.get("name"),
        avatar_url=info.get("picture"),
    )
    return _finish_oauth(request, response, user)


@router.get("/github")
def github_login() -> RedirectResponse:
    _ensure_provider_configured("github")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "read:user user:email",
        "state": _make_state("github"),
        "allow_signup": "true",
    }
    return RedirectResponse(f"{GITHUB_AUTH_URL}?{urlencode(params)}", status_code=status.HTTP_302_FOUND)


@router.get("/github/callback")
async def github_callback(
    request: Request,
    response: Response,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    _ensure_provider_configured("github")
    if error:
        return _frontend_redirect(error="github_cancelled")
    if not code:
        return _frontend_redirect(error="github_missing_code")
    if not _check_state(state, "github"):
        return _frontend_redirect(error="invalid_state")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "redirect_uri": settings.github_redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_response.status_code >= 400:
                logger.warning("GitHub token exchange failed: %s", token_response.text[:200])
                return _frontend_redirect(error="github_failed")
            access_token = token_response.json().get("access_token")
            if not access_token:
                return _frontend_redirect(error="github_failed")
            info_response = await client.get(
                f"{GITHUB_API_URL}/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if info_response.status_code >= 400:
                return _frontend_redirect(error="github_failed")
            info = info_response.json()
            emails = await client.get(
                f"{GITHUB_API_URL}/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            email = info.get("email")
            if emails.status_code < 400:
                for item in emails.json() or []:
                    if item.get("primary") and item.get("email"):
                        email = item["email"]
                        break
    except httpx.HTTPError as exc:
        logger.warning("GitHub OAuth request error: %s", exc)
        return _frontend_redirect(error="github_failed")

    email = (email or "").strip().lower()
    if not email:
        return _frontend_redirect(error="github_no_email")
    user = _upsert_oauth_user(
        provider="github",
        provider_id=str(info.get("id") or email),
        email=email,
        name=info.get("name") or info.get("login"),
        avatar_url=info.get("avatar_url"),
    )
    return _finish_oauth(request, response, user)
