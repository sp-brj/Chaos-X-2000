from __future__ import annotations

import os
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import desc, select

from app.db import session_scope
from app.google_sheets import sync_items_to_google_sheet
from app.models import Item


def _bool_env(name: str, default: bool) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _cron_hour_minute() -> tuple[int, int]:
    """
    Env override: GOOGLE_SHEETS_SYNC_TIME="06:00"
    """
    raw = (os.environ.get("GOOGLE_SHEETS_SYNC_TIME") or "06:00").strip()
    try:
        hh, mm = raw.split(":", 1)
        return int(hh), int(mm)
    except Exception:
        return 6, 0


def start_scheduler(*, SessionLocal: Any, timezone: str) -> BackgroundScheduler:
    """
    Starts background scheduler for daily Google Sheets sync.
    - Runs at 06:00 Europe/Moscow by default (override via GOOGLE_SHEETS_SYNC_TIME).
    - Safe no-op if GOOGLE_SHEETS_ID / GOOGLE_SHEETS_SA_JSON_B64 is not set.
    """
    if not _bool_env("GOOGLE_SHEETS_SYNC_ENABLED", True):
        raise RuntimeError("GOOGLE_SHEETS_SYNC_ENABLED=false")

    hour, minute = _cron_hour_minute()

    sched = BackgroundScheduler(timezone=timezone)

    def _job() -> None:
        # Skip if not configured
        if not (os.environ.get("GOOGLE_SHEETS_ID") and os.environ.get("GOOGLE_SHEETS_SA_JSON_B64")):
            return
        with session_scope(SessionLocal) as session:
            q = select(Item).order_by(desc(Item.created_at)).limit(5000)
            items = list(session.execute(q).scalars())
        sync_items_to_google_sheet(items=items)

    trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
    sched.add_job(_job, trigger=trigger, id="google_sheets_daily_sync", replace_existing=True, max_instances=1)
    sched.start()
    return sched

