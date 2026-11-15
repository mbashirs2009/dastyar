"""مدل‌های Pydantic برای ورودی/خروجی API «دستیار»."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from security import normalize_email, sanitize_name, validate_avatar_url, validate_password

Theme = Literal["system", "dark", "light"]
Role = Literal["user", "assistant", "system"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LANGUAGE_RE = re.compile(r"^[a-zA-Z]{2}(-[a-zA-Z]{2,4})?$")


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# کاربر و احراز هویت
# --------------------------------------------------------------------------- #
class UserOut(_Base):
    """شکل کاربر که فرانت‌اند انتظار دارد."""

    id: int
    email: str
    name: str
    avatar_url: str | None = None
    provider: str = "email"
    theme: Theme = "system"
    language: str = "fa"
    created_at: datetime
    is_verified: bool = False


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not EMAIL_RE.match(value):
            raise ValueError("ایمیل معتبر نیست.")
        return value

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = sanitize_name(value)
        if not value:
            raise ValueError("نام نمی‌تواند خالی باشد.")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str, info: object) -> str:
        try:
            data = getattr(info, "data", {}) or {}
            return validate_password(value, email=data.get("email", ""), name=data.get("name", ""))
        except ValueError as e:
            raise ValueError(str(e)) from e


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_new(cls, value: str) -> str:
        try:
            return validate_password(value)
        except ValueError as e:
            raise ValueError(str(e)) from e


class ForgotPasswordIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_new(cls, value: str) -> str:
        try:
            return validate_password(value)
        except ValueError as e:
            raise ValueError(str(e)) from e


class PageOut(BaseModel):
    items: list
    next_cursor: int | None = None


class ProfileUpdate(BaseModel):
    """همه‌ی فیلدها اختیاری‌اند؛ فقط فیلدهای ارسال‌شده تغییر می‌کنند."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=500)
    theme: Theme | None = None
    language: str | None = Field(default=None, min_length=2, max_length=8)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = sanitize_name(value)
        if not value:
            raise ValueError("نام نمی‌تواند خالی باشد.")
        return value

    @field_validator("avatar_url")
    @classmethod
    def _clean_avatar(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_avatar_url(value)
        except ValueError as e:
            raise ValueError(str(e)) from e

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not LANGUAGE_RE.match(value):
            raise ValueError("کد زبان معتبر نیست (مثلاً fa یا en).")
        return value.lower()


# --------------------------------------------------------------------------- #
# گفتگو و پیام
# --------------------------------------------------------------------------- #
class ConversationOut(_Base):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("عنوان نمی‌تواند خالی باشد.")
        return value


class MessageOut(_Base):
    id: int
    role: Role
    content: str
    created_at: datetime


class ChatIn(BaseModel):
    conversation_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=32_000)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("متن پیام نمی‌تواند خالی باشد.")
        return value


# --------------------------------------------------------------------------- #
# عمومی
# --------------------------------------------------------------------------- #
class OkOut(BaseModel):
    ok: bool = True


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    model: str = "دستیار"
