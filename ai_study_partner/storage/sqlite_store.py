"""
SQLite storage backend — default, zero-config, works everywhere.
NOTE: Render free-tier has an ephemeral filesystem.
      Data survives between requests but resets on redeploy.
      Use Supabase backend for production persistence on Render.
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from storage.base import BaseStore

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "studypartner.db")


class SQLiteStore(BaseStore):
    def __init__(self) -> None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with self._con() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS users "
                "(user_id INTEGER PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}')"
            )

    def _con(self) -> sqlite3.Connection:
        return sqlite3.connect(_DB_PATH)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._con() as con:
            row = con.execute(
                "SELECT data FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def upsert_user(self, user_id: int, updates: Dict[str, Any]) -> None:
        existing = self.get_user(user_id) or {}
        existing.update(updates)
        existing["last_active"] = datetime.now().isoformat()
        blob = json.dumps(existing, default=str)
        with self._con() as con:
            con.execute(
                "INSERT INTO users (user_id, data) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
                (user_id, blob),
            )

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT user_id, data FROM users").fetchall()
        return {str(uid): json.loads(blob) for uid, blob in rows}

    def delete_user(self, user_id: int) -> None:
        with self._con() as con:
            con.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
