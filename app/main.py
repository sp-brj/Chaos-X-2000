from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import desc, select

from app.db import get_engine, get_sessionmaker, session_scope
from app.groq import summarize_and_classify, transcribe_audio
from app.models import Base, Item
from app.telegram_api import (
    answer_callback_query,
    download_file_bytes,
    get_file_path,
    send_message,
)

app = FastAPI(title="Chaos H-2000")


@app.on_event("startup")
def _startup() -> None:
    """
    MVP: create tables on startup (no Alembic yet).
    """
    engine = get_engine()
    if not engine:
        app.state.SessionLocal = None
        return
    Base.metadata.create_all(engine)
    app.state.SessionLocal = get_sessionmaker(engine)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


def _require_shortcuts_token(x_shortcuts_token: str | None) -> None:
    expected = os.environ.get("SHORTCUTS_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="SHORTCUTS_TOKEN not configured")
    if x_shortcuts_token != expected:
        raise HTTPException(status_code=401, detail="Bad shortcuts token")


def _require_db() -> Any:
    SessionLocal = getattr(app.state, "SessionLocal", None)
    if SessionLocal is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
    return SessionLocal


def _horizon_from_text(text: str) -> str | None:
    t = (text or "").lower()
    for tag in ("#неделя", "#3мес", "#полгода", "#год"):
        if tag in t:
            return tag
    return None


def _format_items(items: List[Item]) -> Tuple[str, dict[str, Any]]:
    if not items:
        return "Нет открытых задач.", {}

    lines: List[str] = []
    keyboard: List[List[dict[str, str]]] = []

    for i, it in enumerate(items, start=1):
        tag = f" {it.horizon_tag}" if it.horizon_tag else ""
        title = it.title or (it.text.strip()[:80] if it.text else "")
        lines.append(f"{i}) {title}{tag}")
        keyboard.append([{"text": f"✅ Закрыть {i}", "callback_data": f"done:{it.id}"}])

    return "\n".join(lines), {"inline_keyboard": keyboard}


@app.get("/shortcuts/reminders/daily")
def shortcuts_daily(x_shortcuts_token: str | None = Header(default=None)) -> Dict[str, Any]:
    """
    Endpoint for iOS Shortcuts.
    Returns tasks for today (#неделя tasks) in a simple JSON format.
    In MVP we will query Postgres; for now it's a stub.
    """
    _require_shortcuts_token(x_shortcuts_token)
    SessionLocal = _require_db()
    with session_scope(SessionLocal) as session:
        q = (
            select(Item)
            .where(Item.status == "open", Item.kind == "task", Item.horizon_tag == "#неделя")
            .order_by(desc(Item.created_at))
            .limit(100)
        )
        rows = list(session.execute(q).scalars())
    return {"kind": "daily", "timezone": os.environ.get("TZ", "Europe/Moscow"), "horizon": "#неделя", "items": [r.title or r.text for r in rows]}


@app.get("/shortcuts/reminders/weekly")
def shortcuts_weekly(x_shortcuts_token: str | None = Header(default=None)) -> Dict[str, Any]:
    """
    Endpoint for iOS Shortcuts.
    Returns weekly items (#3мес tasks+ideas).
    In MVP we will query Postgres; for now it's a stub.
    """
    _require_shortcuts_token(x_shortcuts_token)
    SessionLocal = _require_db()
    with session_scope(SessionLocal) as session:
        q = (
            select(Item)
            .where(Item.status == "open", Item.horizon_tag == "#3мес", Item.kind.in_(("task", "idea")))
            .order_by(desc(Item.created_at))
            .limit(200)
        )
        rows = list(session.execute(q).scalars())
    return {"kind": "weekly", "timezone": os.environ.get("TZ", "Europe/Moscow"), "horizon": "#3мес", "items": [r.title or r.text for r in rows]}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Dict[str, Any]:
    """
    Telegram will POST updates here (webhook mode).
    We validate secret token (optional but recommended), then handle:
    - /done command (show last 10 tasks) — placeholder for now
    - callback query from "✅ Закрыть" buttons — placeholder

    Next iteration: persist incoming messages into Postgres + enqueue worker jobs.
    """

    secret_expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if secret_expected and x_telegram_bot_api_secret_token != secret_expected:
        raise HTTPException(status_code=401, detail="Bad webhook secret")

    update = await request.json()

    # Callback queries: close tasks
    callback = update.get("callback_query")
    if callback:
        data = (callback.get("data") or "").strip()
        cb_id = callback.get("id")
        msg = callback.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")

        if data.startswith("done:") and cb_id and chat_id:
            SessionLocal = getattr(app.state, "SessionLocal", None)
            if SessionLocal is None:
                await answer_callback_query(cb_id, "БД не настроена")
                return {"ok": True}
            raw_id = data.split("done:", 1)[1].strip()
            try:
                item_id = uuid.UUID(raw_id)
            except Exception:
                await answer_callback_query(cb_id, "Некорректный id")
                return {"ok": True}

            with session_scope(SessionLocal) as session:
                it = session.get(Item, item_id)
                if it and it.status != "closed":
                    it.status = "closed"
                    it.closed_at = datetime.utcnow()
            await answer_callback_query(cb_id, "✅ Закрыто")
        return {"ok": True}

    # Messages: store + (optional) transcribe + summarize
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    message_id = message.get("message_id")

    if not (chat_id and telegram_user_id):
        return {"ok": True}

    if text in ("/start", "/help"):
        await send_message(chat_id, "Х-2000: принято.\n\nПока доступно: /done (список последних 10 задач).")
        return {"ok": True}

    if text.startswith("/done"):
        SessionLocal = getattr(app.state, "SessionLocal", None)
        if SessionLocal is None:
            await send_message(chat_id, "БД не настроена. Добавь DATABASE_URL в Railway и сделай redeploy.")
            return {"ok": True}
        with session_scope(SessionLocal) as session:
            q = (
                select(Item)
                .where(Item.telegram_user_id == telegram_user_id, Item.status == "open", Item.kind == "task")
                .order_by(desc(Item.created_at))
                .limit(10)
            )
            items = list(session.execute(q).scalars())
        msg_text, markup = _format_items(items)
        await send_message(chat_id, msg_text, reply_markup=markup if markup else None)
        return {"ok": True}

    voice = message.get("voice")
    original_text = text
    transcript = None

    if voice and voice.get("file_id"):
        file_id = voice["file_id"]
        file_path = await get_file_path(file_id)
        if file_path:
            audio_bytes = await download_file_bytes(file_path)
            transcript = await transcribe_audio(audio_bytes, filename=file_path.split("/")[-1] or "voice.ogg")
            original_text = transcript or ""

    # If still empty, ignore
    if not original_text.strip():
        return {"ok": True}

    extract = await summarize_and_classify(original_text)
    horizon = extract.get("horizon_tag") or _horizon_from_text(original_text)

    SessionLocal = getattr(app.state, "SessionLocal", None)
    if SessionLocal is None:
        await send_message(chat_id, "БД не настроена. Добавь DATABASE_URL в Railway и сделай redeploy.")
        return {"ok": True}
    with session_scope(SessionLocal) as session:
        it = Item(
            telegram_user_id=int(telegram_user_id),
            telegram_chat_id=int(chat_id),
            source_message_id=int(message_id) if message_id is not None else None,
            kind=extract.get("kind", "task"),
            horizon_tag=horizon,
            title=extract.get("title"),
            summary=extract.get("summary"),
            transcript=transcript,
            text=original_text,
            raw_update=update,
        )
        session.add(it)

    # Minimal ack
    ack_parts = ["Принято."]
    if horizon:
        ack_parts.append(f"Горизонт: {horizon}")
    if extract.get("kind"):
        ack_parts.append(f"Тип: {extract['kind']}")
    await send_message(chat_id, "\n".join(ack_parts))

    # Always return 200 quickly for Telegram
    return {"ok": True}
