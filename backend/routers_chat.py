"""مسیر چت «دستیار» — پاسخ جریانی (SSE).

زنجیره‌ی پیش‌فرض (auto):
    ۱. OpenRouter  — فقط اگر کلید در `.env` باشد
    ۲. Pollinations — رایگان، بدون کلید، سازگار با اینترنت ایران
    ۳. پاسخ نمایشی — اگر همه شکست خوردند

قرارداد خروجی:
    data: <token>\\n\\n
    data: [DONE]\\n\\n
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

import database as db
from auth import CurrentUser
from config import settings
from data.system_prompt import SYSTEM_PROMPT
from schemas import ChatIn

logger = logging.getLogger("dastyar.chat")

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 30
TITLE_MAX_LENGTH = 60
MODEL_LABEL = "دستیار"

DEMO_REPLY = (
    "سلام! من **دستیار** هستم 👋\n\n"
    "اتصال به سرویس‌های مدل برقرار نشد، برای همین این یک پاسخ نمایشی است.\n\n"
    "اینترنت را چک کن (یا اگر فیلترشکن داری برای پنجره‌ی API هم روشن کن) "
    "و دوباره بپرس."
)

STREAM_ERROR_TEXT = "\n\n⚠️ ارتباط با مدل برقرار نشد. لطفاً چند لحظه بعد دوباره تلاش کنید."
EMPTY_REPLY_TEXT = "متأسفم، پاسخی تولید نشد. لطفاً سؤال را به شکل دیگری بپرسید."

# اتصال کوتاه؛ اگر OpenRouter فیلتر بود سریع رد شویم و برویم سراغ Pollinations
CONNECT_TIMEOUT = 4.0
READ_TIMEOUT = 90.0


# --------------------------------------------------------------------------- #
# کمک‌کننده‌های SSE
# --------------------------------------------------------------------------- #
def _sse(text: str) -> str:
    """یک قطعه متن را به قالب SSE تبدیل می‌کند (چندخطی‌ها امن می‌شوند)."""
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(f"data: {line}\n" for line in normalized.split("\n")) + "\n"


def _done() -> str:
    return "data: [DONE]\n\n"


def _chunk_text(text: str, words_per_chunk: int = 3) -> list[str]:
    """تقسیم متن نمایشی به تکه‌های کوچک شبیه توکن‌های مدل."""
    words = re.findall(r"\S+\s*", text)
    if not words:
        return [text]
    groups = [words[i : i + words_per_chunk] for i in range(0, len(words), words_per_chunk)]
    return ["".join(group) for group in groups]


def _make_title(message: str) -> str:
    title = " ".join(message.split())
    if len(title) > TITLE_MAX_LENGTH:
        title = title[:TITLE_MAX_LENGTH].rstrip() + "…"
    return title or db.DEFAULT_TITLE


def _build_llm_messages(conversation_id: int) -> list[dict[str, str]]:
    history = db.list_messages(conversation_id, limit=HISTORY_LIMIT)
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        if item["role"] in ("user", "assistant"):
            messages.append({"role": item["role"], "content": item["content"]})
    return messages


async def _demo_stream() -> AsyncIterator[str]:
    """پاسخ نمایشی کوتاه فارسی."""
    for chunk in _chunk_text(DEMO_REPLY):
        await asyncio.sleep(0.03)
        yield chunk


# --------------------------------------------------------------------------- #
# استریم OpenAI-سازگار (OpenRouter و Pollinations هر دو همین شکل را می‌دهند)
# --------------------------------------------------------------------------- #
async def _openai_sse_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=20.0, pool=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")[:280]
                logger.warning("LLM HTTP %s from %s: %s", response.status_code, url, body)
                raise RuntimeError(f"HTTP {response.status_code}")

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue  # کامنت‌ها مثل «: OPENROUTER PROCESSING»

                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    logger.debug("Skipping malformed SSE payload: %s", data[:120])
                    continue

                if isinstance(event, dict) and event.get("error"):
                    logger.warning("LLM stream error: %s", str(event["error"])[:300])
                    raise RuntimeError("stream error")

                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content


async def _openrouter_stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.frontend_url,
        "X-Title": "Dastyar",
    }
    payload: dict[str, Any] = {
        "model": settings.openrouter_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
    }
    async for token in _openai_sse_stream(url, headers, payload):
        yield token


async def _pollinations_stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """رایگان، بدون کلید — روی اینترنت ایران هم جواب می‌دهد (تست شده)."""
    url = f"{settings.pollinations_base_url}/openai"
    headers = {
        "Content-Type": "application/json",
        "Referer": settings.frontend_url,
    }
    payload: dict[str, Any] = {
        "model": settings.pollinations_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
    }
    async for token in _openai_sse_stream(url, headers, payload):
        yield token


async def _provider_stream(name: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
    if name == "openrouter":
        async for token in _openrouter_stream(messages):
            yield token
    elif name == "pollinations":
        async for token in _pollinations_stream(messages):
            yield token
    elif name == "mock":
        async for token in _demo_stream():
            yield token
    else:  # pragma: no cover
        raise RuntimeError(f"unknown provider {name}")


async def _auto_stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """اولین سرویسی که توکن داد برنده است؛ اگر قبل از اولین توکن شکست بخورد بعدی را می‌آزماییم."""
    for name in settings.provider_chain:
        sent = False
        try:
            async for token in _provider_stream(name, messages):
                sent = True
                yield token
            if sent:
                return
            logger.warning("Provider %s returned empty reply, trying next", name)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            if sent:
                # وسط پاسخ قطع شد؛ با سرویس بعدی از نو شروع نمی‌کنیم (تکرار می‌شد)
                return
            logger.warning("Provider %s failed before first token, trying next", name)
            continue
    # اگر زنجیره خالی ماند (نمی‌شود) demo از خود chain می‌آید


async def _event_stream(conversation_id: int, messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """پاسخ SSE؛ متن تولیدشده در پایان (حتی در صورت قطع اتصال) ذخیره می‌شود."""
    parts: list[str] = []

    try:
        async for chunk in _auto_stream(messages):
            parts.append(chunk)
            yield _sse(chunk)

        if not "".join(parts).strip():
            parts.append(EMPTY_REPLY_TEXT)
            yield _sse(EMPTY_REPLY_TEXT)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Chat stream failed for conversation %s", conversation_id)
        parts.append(STREAM_ERROR_TEXT)
        yield _sse(STREAM_ERROR_TEXT)
    finally:
        answer = "".join(parts).strip()
        if answer:
            try:
                db.add_message(conversation_id, "assistant", answer)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to persist assistant message")

    yield _done()


# --------------------------------------------------------------------------- #
# مسیر
# --------------------------------------------------------------------------- #
@router.post("/chat")
async def chat(payload: ChatIn, user: CurrentUser) -> StreamingResponse:
    conversation = db.get_conversation(payload.conversation_id, user["id"])
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="گفتگو پیدا نشد.",
        )

    db.add_message(conversation["id"], "user", payload.message)

    if conversation["title"] == db.DEFAULT_TITLE:
        db.rename_conversation(conversation["id"], user["id"], _make_title(payload.message))

    messages = _build_llm_messages(conversation["id"])

    return StreamingResponse(
        _event_stream(conversation["id"], messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
