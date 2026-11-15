"""لایه‌ی داده‌ی «دستیار» — SQLite خالص (کتابخانه‌ی استاندارد).

جدول‌ها: users، conversations، messages.
هر تابع یک اتصال کوتاه‌عمر باز می‌کند تا با اجرای هم‌زمان درخواست‌ها در
FastAPI سازگار باشد. ردیف‌ها به‌صورت dict برگردانده می‌شوند.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import os

DB_PATH = Path(os.getenv("DB_PATH") or Path(__file__).resolve().parent / "dastyar.db")
if str(DB_PATH).startswith("/var/data"):
    Path("/var/data").mkdir(parents=True, exist_ok=True)

DEFAULT_TITLE = "گفتگوی جدید"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT,
    name          TEXT    NOT NULL,
    avatar_url    TEXT,
    provider      TEXT    NOT NULL DEFAULT 'email',
    provider_id   TEXT,
    theme         TEXT    NOT NULL DEFAULT 'system',
    language      TEXT    NOT NULL DEFAULT 'fa',
    created_at    TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
    ON users (provider, provider_id)
    WHERE provider_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_user
    ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    jti           TEXT    NOT NULL UNIQUE,
    refresh_jti   TEXT    NOT NULL UNIQUE,
    refresh_hash  TEXT    NOT NULL,
    user_agent    TEXT,
    ip            TEXT,
    created_at    TEXT    NOT NULL,
    last_used_at  TEXT    NOT NULL,
    expires_at    TEXT    NOT NULL,
    revoked_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_jti ON sessions (jti);
CREATE INDEX IF NOT EXISTS idx_sessions_refresh ON sessions (refresh_jti);

CREATE TABLE IF NOT EXISTS rate_limits (
    key          TEXT    NOT NULL,
    window_start TEXT    NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key, window_start)
);

CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    used_at    TEXT
);

CREATE TABLE IF NOT EXISTS email_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    used_at    TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    action     TEXT    NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    created_at TEXT    NOT NULL,
    details    TEXT
);
"""

USER_FIELDS = "id, email, name, avatar_url, provider, theme, language, created_at, is_verified"
CONVERSATION_FIELDS = "id, title, created_at, updated_at"
MESSAGE_FIELDS = "id, role, content, created_at"


def utcnow() -> str:
    """زمان فعلی UTC به‌صورت ISO-8601 (قابل تجزیه برای جاوااسکریپت)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """اتصال کوتاه‌عمر با commit/rollback خودکار."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """ساخت جدول‌ها و ایندکس‌ها در صورت نبود + مهاجرت ستون‌های جدید."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        # مهاجرت نرم برای دیتابیس‌های قدیمی
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "is_verified" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0")


# --------------------------------------------------------------------------- #
# کاربران
# --------------------------------------------------------------------------- #
def create_user(
    *,
    email: str,
    name: str,
    password_hash: str | None = None,
    provider: str = "email",
    provider_id: str | None = None,
    avatar_url: str | None = None,
    theme: str = "system",
    language: str = "fa",
) -> dict[str, Any]:
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users
                (email, password_hash, name, avatar_url, provider, provider_id,
                 theme, language, created_at, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email, password_hash, name, avatar_url, provider, provider_id,
             theme, language, now, 0),
        )
        user_id = int(cur.lastrowid)
    user = get_user(user_id)
    assert user is not None  # تازه ساخته شده است
    return user


def get_user(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {USER_FIELDS} FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_password_hash(user_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["password_hash"] if row else None


def get_user_by_oauth(provider: str, provider_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {USER_FIELDS} FROM users WHERE provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
    return dict(row) if row else None


def update_user(user_id: int, **fields: Any) -> dict[str, Any] | None:
    """به‌روزرسانی فیلدهای مجاز کاربر."""
    allowed = {"name", "avatar_url", "theme", "language", "provider", "provider_id",
               "password_hash", "email"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_user(user_id)

    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = [*updates.values(), user_id]
    with connect() as conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", values)
    return get_user(user_id)


# --------------------------------------------------------------------------- #
# گفتگوها
# --------------------------------------------------------------------------- #
def list_conversations(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {CONVERSATION_FIELDS}
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_conversation(user_id: int, title: str = DEFAULT_TITLE) -> dict[str, Any]:
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title.strip() or DEFAULT_TITLE, now, now),
        )
        conversation_id = int(cur.lastrowid)
    conversation = get_conversation(conversation_id, user_id)
    assert conversation is not None
    return conversation


def get_conversation(conversation_id: int, user_id: int) -> dict[str, Any] | None:
    """فقط اگر گفتگو متعلق به همین کاربر باشد برمی‌گردد."""
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT {CONVERSATION_FIELDS}
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def rename_conversation(conversation_id: int, user_id: int, title: str) -> dict[str, Any] | None:
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (title.strip(), now, conversation_id, user_id),
        )
        changed = cur.rowcount
    if not changed:
        return None
    return get_conversation(conversation_id, user_id)


def touch_conversation(conversation_id: int, user_id: int, when: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
            (when or utcnow(), conversation_id, user_id),
        )


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# پیام‌ها
# --------------------------------------------------------------------------- #
def list_messages(
    conversation_id: int, *, limit: int | None = None, oldest_first: bool = True
) -> list[dict[str, Any]]:
    """پیام‌های یک گفتگو؛ با limit، آخرین N پیام برمی‌گردد."""
    query = f"SELECT {MESSAGE_FIELDS} FROM messages WHERE conversation_id = ?"
    params: list[Any] = [conversation_id]
    if limit is not None:
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
    else:
        query += " ORDER BY id ASC"

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()

    messages = [dict(row) for row in rows]
    if limit is not None and oldest_first:
        messages.reverse()
    return messages


def add_message(conversation_id: int, role: str, content: str) -> dict[str, Any]:
    """افزودن پیام و به‌روزرسانی زمان گفتگو."""
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, content, now),
        )
        message_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        row = conn.execute(
            f"SELECT {MESSAGE_FIELDS} FROM messages WHERE id = ?", (message_id,)
        ).fetchone()

    assert row is not None
    return dict(row)


def count_messages(conversation_id: int, role: str | None = None) -> int:
    query = "SELECT COUNT(*) AS total FROM messages WHERE conversation_id = ?"
    params: list[Any] = [conversation_id]
    if role is not None:
        query += " AND role = ?"
        params.append(role)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    return int(row["total"]) if row else 0


# --------------------------------------------------------------------------- #
# صفحه‌بندی گفتگوها
# --------------------------------------------------------------------------- #
def list_conversations_paged(
    user_id: int, *, limit: int = 20, cursor: int | None = None
) -> tuple[list[dict[str, Any]], int | None]:
    """کلید مرتب‌سازی: updated_at DESC, id DESC. خروجی: (items, next_cursor)."""
    query = f"SELECT {CONVERSATION_FIELDS} FROM conversations WHERE user_id = ?"
    params: list[Any] = [user_id]
    if cursor is not None:
        query += " AND (updated_at < (SELECT updated_at FROM conversations WHERE id = ?) "
        query += "OR (updated_at = (SELECT updated_at FROM conversations WHERE id = ?) AND id < ?))"
        params.extend([cursor, cursor, cursor])
    query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    items = [dict(row) for row in rows]
    next_cursor = items[-1]["id"] if len(items) == limit else None
    return items, next_cursor


def list_messages_paged(
    conversation_id: int, *, limit: int = 20, cursor: int | None = None
) -> tuple[list[dict[str, Any]], int | None]:
    query = f"SELECT {MESSAGE_FIELDS} FROM messages WHERE conversation_id = ?"
    params: list[Any] = [conversation_id]
    if cursor is not None:
        query += " AND id < ?"
        params.append(cursor)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    items = [dict(row) for row in reversed(rows)]
    next_cursor = items[0]["id"] if len(items) == limit else None
    return items, next_cursor


# --------------------------------------------------------------------------- #
# نشست‌ها (JWT + jti)
# --------------------------------------------------------------------------- #
def create_session(
    *,
    user_id: int,
    jti: str,
    refresh_jti: str,
    refresh_hash: str,
    user_agent: str | None,
    ip: str | None,
    expires_at: str,
) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions
                (user_id, jti, refresh_jti, refresh_hash, user_agent, ip,
                 created_at, last_used_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, jti, refresh_jti, refresh_hash, user_agent, ip, now, now, expires_at),
        )


def get_session_by_jti(jti: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE jti = ?", (jti,)).fetchone()
    return dict(row) if row else None


def get_session_by_refresh_jti(refresh_jti: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE refresh_jti = ?", (refresh_jti,)
        ).fetchone()
    return dict(row) if row else None


def touch_session(jti: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET last_used_at = ? WHERE jti = ?", (utcnow(), jti)
        )


def revoke_session(jti: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE jti = ? AND revoked_at IS NULL",
            (utcnow(), jti),
        )


def revoke_all_user_sessions(user_id: int, *, except_jti: str | None = None) -> None:
    now = utcnow()
    with connect() as conn:
        if except_jti:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND jti != ?",
                (now, user_id, except_jti),
            )
        else:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )


def rotate_session(old_refresh_jti: str, *, new_jti: str, new_refresh_jti: str, new_refresh_hash: str) -> None:
    now = utcnow()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE refresh_jti = ?", (old_refresh_jti,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.execute(
            """
            INSERT INTO sessions
                (user_id, jti, refresh_jti, refresh_hash, user_agent, ip,
                 created_at, last_used_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row["user_id"], new_jti, new_refresh_jti, new_refresh_hash,
             row["user_agent"], row["ip"], now, now, row["expires_at"]),
        )


# --------------------------------------------------------------------------- #
# محدودیت نرخ
# --------------------------------------------------------------------------- #
def rate_hit(key: str, max_count: int, window_seconds: int) -> bool:
    """True اگر مجاز باشد. پنجره‌ی ثابت بر اساس زمان."""
    now = int(time.time())
    window = now - (now % window_seconds)
    window_start = datetime.fromtimestamp(window, tz=timezone.utc).isoformat()
    with connect() as conn:
        row = conn.execute(
            "SELECT count FROM rate_limits WHERE key = ? AND window_start = ?",
            (key, window_start),
        ).fetchone()
        current = int(row["count"]) if row else 0
        if current >= max_count:
            return False
        conn.execute(
            """
            INSERT INTO rate_limits (key, window_start, count) VALUES (?, ?, 1)
            ON CONFLICT (key, window_start) DO UPDATE SET count = count + 1
            """,
            (key, window_start),
        )
    return True


def cleanup_rate_limits() -> None:
    cutoff = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).isoformat()
    with connect() as conn:
        conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))


# --------------------------------------------------------------------------- #
# بازیابی رمز / تأیید ایمیل / audit
# --------------------------------------------------------------------------- #
def create_password_reset(user_id: int, token_hash: str, expires_at: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO password_resets (user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token_hash, utcnow(), expires_at),
        )


def get_valid_password_reset(token_hash: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM password_resets WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (token_hash, utcnow()),
        ).fetchone()
    return dict(row) if row else None


def use_password_reset(token_hash: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (utcnow(), token_hash)
        )


def create_email_token(user_id: int, token_hash: str, expires_at: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO email_tokens (user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token_hash, utcnow(), expires_at),
        )


def use_email_token(token_hash: str) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM email_tokens WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (token_hash, utcnow()),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE email_tokens SET used_at = ? WHERE id = ?", (utcnow(), row["id"])
        )
        conn.execute(
            "UPDATE users SET is_verified = 1 WHERE id = ?", (row["user_id"],)
        )
        return int(row["user_id"])


def add_audit(user_id: int | None, action: str, ip: str | None = None, user_agent: str | None = None, details: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, ip, user_agent, created_at, details) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, ip, user_agent, utcnow(), details),
        )
