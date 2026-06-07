"""
Lightweight JSON-file session store.
Each Telegram user_id maps to a dict of user state.
"""
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")


def _load() -> Dict[str, Any]:
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    if not os.path.exists(_DATA_FILE):
        return {}
    try:
        with open(_DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(users: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    with open(_DATA_FILE, "w") as f:
        json.dump(users, f, indent=2, default=str)


def get_user(user_id: int) -> Optional[Dict]:
    return _load().get(str(user_id))


def update_user(user_id: int, updates: Dict) -> None:
    users = _load()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {}
    users[uid].update(updates)
    users[uid]["last_active"] = datetime.now().isoformat()
    _save(users)


def get_all_users() -> Dict[str, Any]:
    return _load()


def is_onboarded(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("onboarding_step") == "complete")


def get_quiz_state(user_id: int) -> Optional[Dict]:
    user = get_user(user_id)
    return user.get("quiz_state") if user else None


def set_quiz_state(user_id: int, state: Optional[Dict]) -> None:
    update_user(user_id, {"quiz_state": state})
