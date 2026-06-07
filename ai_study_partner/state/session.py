"""
Public session API — all callers use these functions.
The actual storage backend is swapped via STORAGE_BACKEND env var.
"""
from typing import Any, Dict, Optional
from storage.factory import get_store


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    return get_store().get_user(user_id)


def update_user(user_id: int, updates: Dict[str, Any]) -> None:
    get_store().upsert_user(user_id, updates)


def delete_user(user_id: int) -> None:
    get_store().delete_user(user_id)


def get_all_users() -> Dict[str, Dict[str, Any]]:
    return get_store().get_all_users()


def is_onboarded(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("onboarding_step") == "complete")


def get_quiz_state(user_id: int) -> Optional[Dict]:
    user = get_user(user_id)
    return user.get("quiz_state") if user else None


def set_quiz_state(user_id: int, state: Optional[Dict]) -> None:
    update_user(user_id, {"quiz_state": state})
