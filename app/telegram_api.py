from __future__ import annotations

import os
from typing import Any

import httpx


def _bot_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _api_base() -> str:
    token = _bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    return f"https://api.telegram.org/bot{token}"


async def send_message(
    chat_id: int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    # Best possible "mark as accepted", since bots cannot edit user messages.
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{_api_base()}/sendMessage", json=payload)
        r.raise_for_status()


async def answer_callback_query(callback_query_id: str, text: str | None = None) -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{_api_base()}/answerCallbackQuery", json=payload)
        r.raise_for_status()


async def get_file_path(file_id: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{_api_base()}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        data = r.json()
        return (data.get("result") or {}).get("file_path") or ""


async def download_file_bytes(file_path: str) -> bytes:
    token = _bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content

