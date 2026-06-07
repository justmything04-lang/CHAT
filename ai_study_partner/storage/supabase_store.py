"""
Supabase storage backend — recommended for production on Render.
Free tier: 500 MB, unlimited rows.

Setup: run supabase_setup.sql in your Supabase SQL editor first.
Required env vars: SUPABASE_URL, SUPABASE_KEY
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from storage.base import BaseStore


class SupabaseStore(BaseStore):
    def __init__(self) -> None:
        try:
            from supabase import create_client
        except ImportError:
            raise ImportError(
                "supabase package required: pip install supabase\n"
                "Or set STORAGE_BACKEND=sqlite to use the default backend."
            )
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        self._db = create_client(url, key)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        resp = self._db.table("users").select("data").eq("user_id", user_id).execute()
        if resp.data:
            raw = resp.data[0]["data"]
            return raw if isinstance(raw, dict) else json.loads(raw)
        return None

    def upsert_user(self, user_id: int, updates: Dict[str, Any]) -> None:
        existing = self.get_user(user_id) or {}
        existing.update(updates)
        existing["last_active"] = datetime.now().isoformat()
        self._db.table("users").upsert(
            {"user_id": user_id, "data": existing},
            on_conflict="user_id",
        ).execute()

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        resp = self._db.table("users").select("user_id, data").execute()
        result = {}
        for row in resp.data or []:
            raw = row["data"]
            result[str(row["user_id"])] = raw if isinstance(raw, dict) else json.loads(raw)
        return result

    def delete_user(self, user_id: int) -> None:
        self._db.table("users").delete().eq("user_id", user_id).execute()
