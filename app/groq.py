from __future__ import annotations

import json
import os
from typing import Any, Literal, TypedDict

import httpx


GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqExtract(TypedDict):
    kind: Literal["task", "idea", "note"]
    horizon_tag: str | None
    title: str | None
    summary: str | None


def _groq_key() -> str | None:
    return os.environ.get("GROQ_API_KEY")


def _horizon_from_text(text: str) -> str | None:
    t = text.lower()
    for tag in ("#неделя", "#3мес", "#полгода", "#год"):
        if tag in t:
            return tag
    return None


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
    model: str = "whisper-large-v3",
) -> str:
    """
    Groq OpenAI-compatible transcription endpoint.
    """
    key = _groq_key()
    if not key:
        return ""

    headers = {"Authorization": f"Bearer {key}"}
    files = {"file": (filename, audio_bytes, "application/octet-stream")}
    data = {"model": model}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{GROQ_BASE_URL}/audio/transcriptions", headers=headers, data=data, files=files)
        r.raise_for_status()
        payload = r.json()
        # OpenAI-style response: {"text": "..."}
        return (payload.get("text") or "").strip()


async def summarize_and_classify(
    text: str,
    *,
    model: str = "llama-3.1-8b-instant",
) -> GroqExtract:
    """
    Returns a conservative extract without "inventing" content.
    """
    horizon = _horizon_from_text(text)
    key = _groq_key()
    if not key:
        # Fallback: no LLM, minimal heuristics
        return {
            "kind": "task",
            "horizon_tag": horizon,
            "title": (text.strip()[:120] or None),
            "summary": None,
        }

    system = (
        "Ты извлекаешь метаданные и короткое саммари, НЕ искажая смысл.\n"
        "Правила:\n"
        "- Ничего не придумывай.\n"
        "- По возможности используй формулировки пользователя (минимум перефразирования).\n"
        "- kind строго одно из: task | idea | note.\n"
        "- horizon_tag строго одно из: #неделя | #3мес | #полгода | #год | null.\n"
        "- title: 3–10 слов, по сути.\n"
        "- summary: 1–3 короткие строки, без воды.\n"
        "Верни ТОЛЬКО JSON-объект с ключами: kind, horizon_tag, title, summary."
    )

    headers = {"Authorization": f"Bearer {key}"}
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{GROQ_BASE_URL}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or "{}"
        try:
            obj = json.loads(content)
        except Exception:
            obj = {}

    kind = obj.get("kind") if obj.get("kind") in ("task", "idea", "note") else "task"
    horizon_tag = obj.get("horizon_tag") if obj.get("horizon_tag") in ("#неделя", "#3мес", "#полгода", "#год") else None
    if not horizon_tag:
        horizon_tag = horizon

    title = obj.get("title")
    summary = obj.get("summary")

    return {
        "kind": kind,
        "horizon_tag": horizon_tag,
        "title": title if isinstance(title, str) and title.strip() else None,
        "summary": summary if isinstance(summary, str) and summary.strip() else None,
    }

