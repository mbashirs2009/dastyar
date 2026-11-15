"""مسیرهای مدیریت گفتگوها (CRUD) برای «دستیار»."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

import database as db
from auth import CurrentUser
from schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    OkOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

NOT_FOUND = "گفتگو پیدا نشد."


def _require_conversation(conversation_id: int, user_id: int) -> dict:
    conversation = db.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return conversation


@router.get("")
def list_conversations(
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    if limit > 100:
        raise HTTPException(status_code=422, detail="limit حداکثر ۱۰۰ است.")
    items, next_cursor = db.list_conversations_paged(user["id"], limit=limit, cursor=cursor)
    return {
        "items": [ConversationOut.model_validate(i) for i in items],
        "next_cursor": next_cursor,
    }


@router.post("", response_model=ConversationOut)
def create_conversation(
    user: CurrentUser, payload: ConversationCreate | None = None
) -> ConversationOut:
    title = (payload.title if payload else None) or db.DEFAULT_TITLE
    conversation = db.create_conversation(user["id"], title.strip() or db.DEFAULT_TITLE)
    return ConversationOut.model_validate(conversation)


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=0),
) -> dict:
    _require_conversation(conversation_id, user["id"])
    if limit > 100:
        raise HTTPException(status_code=422, detail="limit حداکثر ۱۰۰ است.")
    items, next_cursor = db.list_messages_paged(conversation_id, limit=limit, cursor=cursor)
    return {
        "items": [MessageOut.model_validate(i) for i in items],
        "next_cursor": next_cursor,
    }


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: int, payload: ConversationUpdate, user: CurrentUser
) -> ConversationOut:
    conversation = db.rename_conversation(conversation_id, user["id"], payload.title)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}", response_model=OkOut)
def delete_conversation(conversation_id: int, user: CurrentUser) -> OkOut:
    if not db.delete_conversation(conversation_id, user["id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return OkOut(ok=True)
