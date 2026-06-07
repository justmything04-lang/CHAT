"""
Returns the correct storage backend singleton based on STORAGE_BACKEND env var.
  sqlite   — default, zero-config, file-based (ephemeral on Render free tier)
  supabase — production-ready, free 500 MB tier, persistent on Render
  gsheet   — educational, uses Google Sheet as flat DB (slow, great for demos)
"""
import os
from storage.base import BaseStore

_store: BaseStore | None = None


def get_store() -> BaseStore:
    global _store
    if _store is not None:
        return _store

    backend = os.getenv("STORAGE_BACKEND", "sqlite").lower()

    if backend == "supabase":
        from storage.supabase_store import SupabaseStore
        _store = SupabaseStore()
    elif backend == "gsheet":
        from storage.gsheet_store import GSheetStore
        _store = GSheetStore()
    elif backend == "sqlite":
        from storage.sqlite_store import SQLiteStore
        _store = SQLiteStore()
    else:
        raise ValueError(
            f"Unknown STORAGE_BACKEND='{backend}'. "
            "Valid options: sqlite, supabase, gsheet"
        )
    return _store
