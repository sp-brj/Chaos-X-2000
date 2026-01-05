from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Header, HTTPException, Request


app = FastAPI(title="Chaos H-2000")


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}

def _require_shortcuts_token(x_shortcuts_token: str | None) -> None:
    expected = os.environ.get("SHORTCUTS_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="SHORTCUTS_TOKEN not configured")
    if x_shortcuts_token != expected:
        raise HTTPException(status_code=401, detail="Bad shortcuts token")


@app.get("/shortcuts/reminders/daily")
def shortcuts_daily(x_shortcuts_token: str | None = Header(default=None)) -> Dict[str, Any]:
    """
    Endpoint for iOS Shortcuts.
    Returns tasks for today (#неделя tasks) in a simple JSON format.
    In MVP we will query Postgres; for now it's a stub.
    """
    _require_shortcuts_token(x_shortcuts_token)
    return {
        "kind": "daily",
        "timezone": os.environ.get("TZ", "Europe/Moscow"),
        "horizon": "#неделя",
        "items": [],
    }


@app.get("/shortcuts/reminders/weekly")
def shortcuts_weekly(x_shortcuts_token: str | None = Header(default=None)) -> Dict[str, Any]:
    """
    Endpoint for iOS Shortcuts.
    Returns weekly items (#3мес tasks+ideas).
    In MVP we will query Postgres; for now it's a stub.
    """
    _require_shortcuts_token(x_shortcuts_token)
    return {
        "kind": "weekly",
        "timezone": os.environ.get("TZ", "Europe/Moscow"),
        "horizon": "#3мес",
        "items": [],
    }


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

    # Minimal behavior: reply to /start, /help, /done with a stub message
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id and text in ("/start", "/help"):
        await _tg_send_message(
            chat_id,
            "Х-2000: принято.\n\nПока доступно: /done (заглушка).",
        )

    if chat_id and text.startswith("/done"):
        await _tg_send_message(
            chat_id,
            "Скоро здесь будет список последних 10 задач с кнопками ✅ Закрыть.",
        )

    # Always return 200 quickly for Telegram
    return {"ok": True}


async def _tg_send_message(chat_id: int, text: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Telegram sendMessage failed: {r.status_code} {r.text}")


