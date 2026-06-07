"""
Google Sheets storage backend — uses a separate "meta" spreadsheet as a flat DB.
Educational option: makes all user data visible and inspectable in a sheet.

WARNING: Slow (~300-500ms per read/write). Suitable for demo / low-traffic use.
Required env var: GSHEET_DB_ID (the spreadsheet ID of your admin/meta sheet)
The sheet must have a tab named "Users" with columns: user_id | data
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import gspread

from storage.base import BaseStore

_TAB = "Users"
_HEADERS = ["user_id", "data"]


def _client() -> gspread.Client:
    creds_file = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    return gspread.service_account(filename=creds_file)


class GSheetStore(BaseStore):
    def __init__(self) -> None:
        sheet_id = os.environ["GSHEET_DB_ID"]
        gc = _client()
        self._ss = gc.open_by_key(sheet_id)
        self._ws = self._ensure_tab()

    def _ensure_tab(self):
        try:
            ws = self._ss.worksheet(_TAB)
        except gspread.WorksheetNotFound:
            ws = self._ss.add_worksheet(_TAB, rows=1000, cols=2)
            ws.append_row(_HEADERS)
        return ws

    def _all_rows(self) -> list:
        return self._ws.get_all_records()

    def _row_index(self, user_id: int) -> Optional[int]:
        all_values = self._ws.get_all_values()
        for i, row in enumerate(all_values[1:], start=2):
            if row and str(row[0]) == str(user_id):
                return i
        return None

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        for row in self._all_rows():
            if str(row.get("user_id", "")) == str(user_id):
                raw = row.get("data", "{}")
                return json.loads(raw) if isinstance(raw, str) else raw
        return None

    def upsert_user(self, user_id: int, updates: Dict[str, Any]) -> None:
        existing = self.get_user(user_id) or {}
        existing.update(updates)
        existing["last_active"] = datetime.now().isoformat()
        blob = json.dumps(existing, default=str)
        idx = self._row_index(user_id)
        if idx:
            self._ws.update_cell(idx, 2, blob)
        else:
            self._ws.append_row([str(user_id), blob])

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        for row in self._all_rows():
            uid = str(row.get("user_id", ""))
            raw = row.get("data", "{}")
            if uid:
                result[uid] = json.loads(raw) if isinstance(raw, str) else raw
        return result

    def delete_user(self, user_id: int) -> None:
        idx = self._row_index(user_id)
        if idx:
            self._ws.delete_rows(idx)
