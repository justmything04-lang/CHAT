"""
Exports Tab 1 (DASHBOARD) as a PNG via Google's Sheets export API.
Sends the image to the user on Telegram.

Strategy: authenticated GET to the spreadsheet export endpoint using
the service account OAuth2 token — no extra API enabling needed.
"""
import io
import logging
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
_EXPORT_RANGE = "A1:I38"
_SCALE = 2


def _get_token() -> str:
    creds_file = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    creds = Credentials.from_service_account_file(creds_file, scopes=_SCOPES)
    creds.refresh(Request())
    return creds.token


def fetch_dashboard_png(spreadsheet_id: str) -> bytes:
    """Return PNG bytes of Tab 1 (gid=0). Raises on failure."""
    token = _get_token()
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
        f"?format=png&range={_EXPORT_RANGE}&gid=0&scale={_SCALE}"
    )
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


async def send_dashboard_snapshot(bot, chat_id: int, spreadsheet_id: str,
                                   sheet_url: str = "") -> bool:
    """Fetch dashboard PNG and send it to the user. Returns True on success."""
    try:
        png_bytes = fetch_dashboard_png(spreadsheet_id)
        img = io.BytesIO(png_bytes)
        img.name = "dashboard.png"

        caption = "📊 *Your Study Dashboard*"
        if sheet_url:
            caption += f"\n[Open full sheet ↗]({sheet_url})"

        await bot.send_photo(
            chat_id=chat_id,
            photo=img,
            caption=caption,
            parse_mode="Markdown",
        )
        return True
    except Exception as exc:
        logger.error("Snapshot failed for %s: %s", chat_id, exc)
        return False
