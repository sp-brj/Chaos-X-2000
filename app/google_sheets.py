from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.models import Item


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
REQUIRED_TABS = ["Неделя", "Месяц", "Квартал", "Год", "Идея", "Мысли"]


def _a1(tab_name: str, a1: str) -> str:
    """
    Build safe A1 range for sheet tabs, including non-ASCII names.
    Google Sheets API expects tab names with special chars/spaces/non-latin to be quoted:
      'Неделя'!A:Z
    Single quotes inside names must be doubled.
    """
    safe_tab = (tab_name or "").replace("'", "''")
    return f"'{safe_tab}'!{a1}"


def _sheet_id() -> str | None:
    return os.environ.get("GOOGLE_SHEETS_ID")


def _service_account_info() -> dict[str, Any] | None:
    """
    Prefer base64 JSON in env to avoid multiline secrets problems.
    Env:
      - GOOGLE_SHEETS_SA_JSON_B64: base64(service_account_json)
      - GOOGLE_SHEETS_SA_JSON: raw JSON string (fallback)
    """
    b64 = os.environ.get("GOOGLE_SHEETS_SA_JSON_B64")
    if b64:
        try:
            return json.loads(base64.b64decode(b64).decode("utf-8"))
        except Exception:
            return None
    raw = os.environ.get("GOOGLE_SHEETS_SA_JSON")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None


def _sheets_client() -> Any:
    info = _service_account_info()
    if not info:
        raise RuntimeError("Google Sheets service account not configured (GOOGLE_SHEETS_SA_JSON_B64)")
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _ensure_tabs_exist(*, svc: Any, spreadsheet_id: str, tabs: list[str]) -> None:
    """
    Ensure the spreadsheet contains all required sheet tabs.
    If missing, create via batchUpdate(addSheet).
    """
    meta = (
        svc.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
        .execute()
    )
    existing = {(((s.get("properties") or {}).get("title")) or "") for s in (meta.get("sheets") or [])}
    missing = [t for t in tabs if t not in existing]
    if not missing:
        return

    requests: list[dict[str, Any]] = [{"addSheet": {"properties": {"title": t}}} for t in missing]
    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()


def _tab_for_item(it: Item) -> str:
    """
    Tabs in Google Sheet:
      Неделя / Месяц / Квартал / Год / Идея / Мысли
    """
    if it.kind == "idea":
        return "Идея"
    if it.kind == "note":
        return "Мысли"

    # tasks
    tag = (it.horizon_tag or "").lower()
    if tag == "#неделя":
        return "Неделя"
    if tag == "#месяц":
        return "Месяц"
    if tag == "#квартал":
        return "Квартал"
    if tag == "#год":
        return "Год"
    # default for tasks without horizon
    return "Неделя"


@dataclass(frozen=True)
class SheetRow:
    values: list[Any]


def _rows_for_items(items: Iterable[Item]) -> dict[str, list[SheetRow]]:
    """
    Group items by sheet tab.
    Columns (v1, user-facing):
      status | title | text
    """
    grouped: dict[str, list[SheetRow]] = {}
    for it in items:
        tab = _tab_for_item(it)
        title = (it.title or "").strip()
        if not title:
            title = ((it.text or "").strip()[:80]) if it.text else ""
        grouped.setdefault(tab, []).append(
            SheetRow(
                values=[
                    it.status,
                    title,
                    (it.text or "").strip(),
                ]
            )
        )
    return grouped


def sync_items_to_google_sheet(*, items: list[Item]) -> dict[str, Any]:
    """
    Minimal v1 sync:
    - Writes full snapshot per tab (clear + header + rows).
    - Keeps done items (status=closed) as rows; UI can strike-through via conditional formatting (added later).
    """
    sheet_id = _sheet_id()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEETS_ID not configured")

    svc = _sheets_client()
    grouped = _rows_for_items(items)
    # Ensure tabs exist even if spreadsheet is fresh / has different default names.
    _ensure_tabs_exist(svc=svc, spreadsheet_id=sheet_id, tabs=REQUIRED_TABS)

    headers = ["status", "title", "text"]

    updates = 0
    for tab, rows in grouped.items():
        # clear tab
        svc.spreadsheets().values().clear(spreadsheetId=sheet_id, range=_a1(tab, "A:Z"), body={}).execute()
        body = {"values": [headers] + [r.values for r in rows]}
        svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=_a1(tab, "A1"),
            valueInputOption="RAW",
            body=body,
        ).execute()
        updates += 1

    return {"ok": True, "tabs_updated": updates, "tabs": sorted(grouped.keys())}

