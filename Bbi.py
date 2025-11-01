# one_click_daily_updates.py — One-click attendance with parent updates (Telegram + WhatsApp invite)

import os
import time
import json
import math
import gspread
import telebot
import threading
import requests
from collections import deque
from flask import Flask, request
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from telebot import types
import calendar  # for month boundaries

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from os import getenv


# ---- Bi-Weekly + formatting imports ----
try:
    from dateutil.parser import parse as _dateparse
except Exception:
    _dateparse = None

try:
    from gspread_formatting import set_frozen, format_cell_ranges, CellFormat, Color, TextFormat
except Exception:
    # colouring is optional; we’ll no-op if not installed
    set_frozen = format_cell_ranges = CellFormat = Color = TextFormat = None

# No need to change requirements now; colouring auto-skips if the package isn't installed.


# ---------------- Load env ----------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
ABSENTEE_SHEET_ID = os.getenv("ABSENTEE_SHEET_ID")
ONLINE_ABSENTEE_SHEET_ID = os.getenv("ONLINE_ABSENTEE_SHEET_ID")
TEACHER_ID = os.getenv("TEACHER_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()  # for deep link

TIMEZONE = os.getenv("TIMEZONE", "UTC")
CLASS_LAT = float(os.getenv("CLASS_LAT", 0))
CLASS_LON = float(os.getenv("CLASS_LON", 0))
RADIUS_METERS = float(os.getenv("RADIUS_METERS", 100))
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL", "")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY", "").strip()
MSG91_WHATSAPP_SENDER_ID = os.getenv("MSG91_WHATSAPP_SENDER_ID", "").strip()
MSG91_WHATSAPP_TEMPLATE_ID_PARENT_INVITE = os.getenv("MSG91_WHATSAPP_TEMPLATE_ID_PARENT_INVITE", "").strip()
MSG91_TEMPLATE_LANG = os.getenv("MSG91_TEMPLATE_LANG", "en_US").strip()
APP_STUDENT_HIGH = getenv("APP_STUDENT_HIGH")
APP_PARENT_HIGH = getenv("APP_PARENT_HIGH")
APP_STUDENT_TOP3 = getenv("APP_STUDENT_TOP3")
APP_PARENT_TOP3 = getenv("APP_PARENT_TOP3")
DAILY_MSG = getenv("DAILY_MSG")
# ─── Absence Streak Messages ────────────────────────────────
ABSENCE_1_MSG = getenv("ABSENCE_1_MSG")
ABSENCE_2_MSG = getenv("ABSENCE_2_MSG")
ABSENCE_3_MSG = getenv("ABSENCE_3_MSG")
ABSENCE_5_MSG = getenv("ABSENCE_5_MSG")
ABSENCE_10_MSG = getenv("ABSENCE_10_MSG")
ABSENCE_ALERT_MSG = getenv("ABSENCE_ALERT_MSG")



# Message templates from ENV (editable without redeploy)
TPL_PARENT_WELCOME = os.getenv("PARENT_WELCOME_MSG",
    "Hello 👋, you are now linked as a parent for updates about your child’s attendance. Please do not reply.")
TPL_PARENT_ABSENT = os.getenv("PARENT_ABSENT_MSG",
    "⚠️ Your child {student_name} ({reg_id}) was absent on {date} ({mode}).")
TPL_PARENT_INVITE = os.getenv("PARENT_INVITE_MSG",
    "Hello 👋 from the academy. Please install Telegram and start our bot to receive updates: https://t.me/{bot_username}?start=parent_{reg_id}")
TPL_FACULTY_WEEKLY = os.getenv("FACULTY_REPORT_MSG",
    "📊 Weekly Report:\nOffline parents linked: {off_linked}/{off_total}\nOnline parents linked: {on_linked}/{on_total}")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ---------------- Safe Telegram helpers ----------------
TELEGRAM_TEXT_LIMIT = 3900

def _truncate_text(text):
    if not isinstance(text, str):
        return text
    if len(text) <= TELEGRAM_TEXT_LIMIT:
        return text
    head = text[:1800]
    tail = text[-1800:]
    return head + "\n\n...[truncated]...\n\n" + tail

def safe_reply(message_obj, text, **kwargs):
    try:
        safe_text = _truncate_text(text)
        return bot.reply_to(message_obj, safe_text, **kwargs)
    except Exception as e:
        try:
            chat_id = getattr(message_obj, "chat", {}).get("id", None) or getattr(message_obj.from_user, "id", None)
            if chat_id:
                safe_text = _truncate_text(text)
                return bot.send_message(chat_id, safe_text, **kwargs)
        except Exception:
            pass
        print("⚠️ safe_reply error:", e)
        return None

def safe_send_chat(chat_id, text, **kwargs):
    try:
        safe_text = _truncate_text(text)
        return bot.send_message(chat_id, safe_text, **kwargs)
    except Exception as e:
        print("⚠️ safe_send_chat error:", e)
        return None



# ---------------- MSG91 WhatsApp Helper (bulk/template schema) ----------------
import re
import os
import requests

def send_whatsapp_via_msg91(to_number, template_id=None, variables=None, lang=None, media_url=None):
    """
    Sends a WhatsApp TEMPLATE via MSG91 bulk/template API.

    Uses env:
      MSG91_AUTH_KEY
      MSG91_WHATSAPP_SENDER_ID           # e.g. 919791127514  (NO '+')
      MSG91_WHATSAPP_NAMESPACE           # from template JSON
      MSG91_WHATSAPP_TEMPLATE_NAME       # template *name* (if template_id not passed)
      MSG91_TEMPLATE_LANG                # e.g. en_US (UI shows En_US; either is fine)

    Args:
      to_number   : string, phone with or without +91 (we normalize)
      template_id : optional, if you want to override name via env; here it's the *name* ('kmn')
      variables   : list like ["School", "https://..."], mapped to body_1, body_2 ...
      lang        : optional; ignored by MSG91 if template has fixed language, but we pass it
      media_url   : optional; if your template header is Image, pass a public URL
    """
    auth   = (os.getenv("MSG91_AUTH_KEY") or "").strip()
    sender = (os.getenv("MSG91_WHATSAPP_SENDER_ID") or "").strip()
    ns     = (os.getenv("MSG91_WHATSAPP_NAMESPACE") or "").strip()
    tname  = (template_id or os.getenv("MSG91_WHATSAPP_TEMPLATE_NAME") or "").strip()
    lcode  = (lang or os.getenv("MSG91_TEMPLATE_LANG") or "en_US").strip()

    if not (auth and sender and ns and tname):
        print("❌ MSG91 config missing. Need AUTH_KEY, SENDER_ID, NAMESPACE, TEMPLATE_NAME.")
        return False

    # Normalize recipient to countrycode + number, no '+'
    raw = str(to_number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "91" + digits
    # keep only last 12 in case someone sent +91... or 0091...
    if len(digits) > 12:
        digits = digits[-12:]

    # Build components: body_1..n from variables list
    variables = list(variables or [])
    components = {}
    for i, v in enumerate(variables, start=1):
        components[f"body_{i}"] = {"type": "text", "value": str(v)}

    # Optional header image (ONLY if your template header is Image)
    # If you added image header in the template and want to send it, uncomment:
    # if media_url:
    #     components["header_1"] = {"type": "image", "value": media_url}

    payload = {
        "integrated_number": sender,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": tname,
                "language": {
                    "code": lcode,
                    "policy": "deterministic"
                },
                "namespace": ns,
                "to_and_components": [
                    {
                        "to": [digits],
                        "components": components
                    }
                ]
            }
        }
    }

    url = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"
    headers = {
        "content-type": "application/json",
        "authkey": auth
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        body = resp.text.strip()
        print("📤 MSG91 bulk req:", {"to": digits, "name": tname, "vars": variables})
        print("📥 MSG91 bulk resp:", resp.status_code, body[:600])

        if 200 <= resp.status_code < 300:
            # Common success markers in bulk API:
            try:
                j = resp.json()
                # Look for "type":"success" or "message":"success" or non-empty "data"
                ok = (str(j.get("type", "")).lower() == "success" or
                      str(j.get("message", "")).lower() == "success" or
                      bool(j.get("data")))
                return ok
            except Exception:
                return "success" in body.lower()
        return False
    except Exception as e:
        print("❌ MSG91 bulk send error:", e)
        return False

# ---------------- Google Sheets Auth ----------------
try:
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    client = gspread.authorize(credentials)
    print("✅ Google credentials loaded.")
except Exception as e:
    print("❌ Error loading Google credentials:", e)
    raise

# ---- Google Sheets Read/Write Throttle & Retry (to avoid 429) ----
_last_gs_read = [0.0]
GS_READ_MIN_GAP = float(os.getenv("GS_READ_MIN_GAP", "0.35"))  # seconds between reads
GS_READ_MAX_RETRIES = int(os.getenv("GS_READ_MAX_RETRIES", "5"))
GS_WRITE_MAX_RETRIES = int(os.getenv("GS_WRITE_MAX_RETRIES", "4"))
# jitter factor in seconds (max random jitter)
GS_BACKOFF_JITTER = float(os.getenv("GS_BACKOFF_JITTER", "0.25"))

def _gs_pause():
    import time as _t
    gap = GS_READ_MIN_GAP - (_t.time() - _last_gs_read[0])
    if gap > 0:
        _t.sleep(gap)
    _last_gs_read[0] = _t.time()

def _gs_read(callable_fn, desc=None):
    """
    Throttle + retry wrapper for gspread reads (e.g., ws.get_all_records()).
    - Exponential backoff with jitter on 429 / Rate Limit / 5xx.
    - Returns callable_fn() result or raises last exception.
    - desc: optional short description (for logging).
    """
    import time as _t, random as _r
    desc = (desc or "gs_read")
    for attempt in range(1, GS_READ_MAX_RETRIES + 1):
        try:
            _gs_pause()
            return callable_fn()
        except gspread.exceptions.APIError as e:
            s = str(e)
            if ("429" in s) or ("Rate Limit Exceeded" in s) or ("quota" in s.lower()) or (e.response and 500 <= getattr(e.response, "status_code", 0) < 600):
                backoff = min(0.5 * (2 ** (attempt - 1)), 8.0)
                jitter = _r.random() * GS_BACKOFF_JITTER
                wait = backoff + jitter
                print(f"⚠️ {_t.strftime('%Y-%m-%d %H:%M:%S')} {_gs_read.__name__} attempt {attempt} for {desc} got 429/5xx — backoff {wait:.2f}s")
                _t.sleep(wait)
                continue
            # not a rate/5xx error — re-raise
            raise
        except Exception as e:
            # Non-API errors: small retry but surface quicker
            if attempt < GS_READ_MAX_RETRIES:
                backoff = min(0.5 * (2 ** (attempt - 1)), 4.0)
                jitter = _r.random() * GS_BACKOFF_JITTER
                wait = backoff + jitter
                print(f"⚠️ {_t.strftime('%Y-%m-%d %H:%M:%S')} {_gs_read.__name__} attempt {attempt} for {desc} error: {e} — retrying in {wait:.2f}s")
                _t.sleep(wait)
                continue
            raise
    # raise if all attempts exhausted
    raise RuntimeError(f"{_gs_read.__name__} failed after {GS_READ_MAX_RETRIES} attempts for {desc}.")

def _gs_write(callable_fn, desc=None):
    """
    Retry wrapper for writes (append_rows, update, add_worksheet, batch_clear, etc).
    - Retries on APIError 429/5xx with exponential backoff + jitter.
    - Returns callable_fn() result or raises.
    """
    import time as _t, random as _r
    desc = (desc or "gs_write")
    for attempt in range(1, GS_WRITE_MAX_RETRIES + 1):
        try:
            return callable_fn()
        except gspread.exceptions.APIError as e:
            s = str(e)
            if ("429" in s) or ("Rate Limit Exceeded" in s) or ("quota" in s.lower()) or (e.response and 500 <= getattr(e.response, "status_code", 0) < 600):
                backoff = min(0.5 * (2 ** (attempt - 1)), 10.0)
                jitter = _r.random() * GS_BACKOFF_JITTER
                wait = backoff + jitter
                print(f"⚠️ {_t.strftime('%Y-%m-%d %H:%M:%S')} {_gs_write.__name__} attempt {attempt} for {desc} got 429/5xx — backoff {wait:.2f}s")
                _t.sleep(wait)
                continue
            # not a rate/5xx error — re-raise
            raise
        except Exception as e:
            if attempt < GS_WRITE_MAX_RETRIES:
                backoff = min(0.5 * (2 ** (attempt - 1)), 6.0)
                jitter = _r.random() * GS_BACKOFF_JITTER
                wait = backoff + jitter
                print(f"⚠️ {_t.strftime('%Y-%m-%d %H:%M:%S')} {_gs_write.__name__} attempt {attempt} for {desc} error: {e} — retrying in {wait:.2f}s")
                _t.sleep(wait)
                continue
            raise
    raise RuntimeError(f"{_gs_write.__name__} failed after {GS_WRITE_MAX_RETRIES} attempts for {desc}.")




# ---------------- Sheets (offline + online) ----------------
attendance_sheet = client.open_by_key(SHEET_ID).worksheet("Attendance")
master_sheet = client.open_by_key(SHEET_ID).worksheet("MasterList")
settings_sheet = client.open_by_key(SHEET_ID).worksheet("Settings")

# Online tabs (same workbook)
try:
    online_attendance_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineAttendance")
except Exception:
    online_attendance_sheet = None

try:
    online_master_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineMasterList")
except Exception:
    online_master_sheet = None

# ParentQueue (in main workbook)
try:
    parent_queue_sheet = client.open_by_key(SHEET_ID).worksheet("ParentQueue")
except gspread.exceptions.WorksheetNotFound:
    parent_queue_sheet = client.open_by_key(SHEET_ID).add_worksheet(title="ParentQueue", rows="1000", cols="8")
    parent_queue_sheet.update("A1:H1", [["RegID","Date","Mode","Message","Status","CreatedAt","SentAt","Attempts"]])

# --- Auto-fix duplicate headers once at startup ---
def sanitize_sheet_headers(sheet):
    header = sheet.row_values(1)
    seen = {}
    new_header = []
    changed = False
    for h in header:
        key = (h or "").strip() or "Column"
        if key in seen:
            seen[key] += 1
            new_key = f"{key}_{seen[key]}"
            new_header.append(new_key)
            changed = True
        else:
            seen[key] = 0
            new_header.append(key)
    if changed:
        for col_idx, val in enumerate(new_header, start=1):
            try:
                sheet.update_cell(1, col_idx, val)
            except Exception as e:
                print("sanitize_sheet_headers.update_cell error:", e)
    return new_header

# Run once to sanitize headers
sanitize_sheet_headers(parent_queue_sheet)

# ---------------- Invites sheet (persist one-time links) ----------------
try:
    invites_sheet = client.open_by_key(SHEET_ID).worksheet("Invites")
except gspread.exceptions.WorksheetNotFound:
    invites_sheet = client.open_by_key(SHEET_ID).add_worksheet(title="Invites", rows="2000", cols="8")
    invites_sheet.update("A1:H1", [[
        "InviteLink","GroupId","UserId","Kind","Status","CreatedAt","ExpireAt","UsedAt"
    ]])

# ---------- Persistent "Control" helpers (to avoid multi-process duplicates) ----------
try:
    control_sheet = client.open_by_key(SHEET_ID).worksheet("Control")
except gspread.exceptions.WorksheetNotFound:
    control_sheet = client.open_by_key(SHEET_ID).add_worksheet(title="Control", rows="200", cols="4")
    # header Key | Value | UpdatedAt
    control_sheet.update("A1:C1", [["Key","Value","UpdatedAt"]])

def _control_get(key):
    """Return value (string) for a key or None"""
    try:
        rows = control_sheet.get_all_records()
        for r in rows:
            if str(r.get("Key","")).strip() == str(key):
                return str(r.get("Value","")).strip()
    except Exception as e:
        print("_control_get error:", e)
    return None

def _control_set(key, value):
    """Upsert key->value and UpdatedAt in Control sheet"""
    try:
        rows = control_sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("Key","")).strip() == str(key):
                control_sheet.update_cell(i, 2, str(value))
                control_sheet.update_cell(i, 3, now_ts())
                return True
        # not found -> append
        control_sheet.append_row([str(key), str(value), now_ts()], value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print("_control_set error:", e)
        return False


# ---------------- Simple cache (TTL = 60s) ----------------
CACHE_TTL = 60
_cache = {
    "settings": (None, 0),
    "master": (None, 0),
    "attendance_rows": (None, 0),
    "online_master": (None, 0),
    "online_attendance_rows": (None, 0)
}

def _is_cache_fresh(key):
    val, ts = _cache.get(key, (None, 0))
    return (time.time() - ts) < CACHE_TTL

def invalidate_cache(key=None):
    if key is None:
        for k in _cache.keys():
            _cache[k] = (None, 0)
    else:
        _cache[key] = (None, 0)

def get_cached_settings():
    if _is_cache_fresh("settings"):
        return _cache["settings"][0]
    try:
        s = _gs_read(lambda: settings_sheet.get_all_records())[0]
        _cache["settings"] = (s, time.time())
        return s
    except Exception as e:
        print("⚠️ Error fetching settings:", e)
        return _cache["settings"][0] or {}

def get_cached_master_list():
    if _is_cache_fresh("master"):
        return _cache["master"][0]
    try:
        data = _gs_read(lambda: master_sheet.get_all_records(), desc="master_sheet.get_all_records()")
        _cache["master"] = (data, time.time())
        return data
    except Exception as e:
        print("⚠️ Error fetching master list:", e)
        return _cache["master"][0] or []

def get_cached_online_master_list():
    if _is_cache_fresh("online_master"):
        return _cache["online_master"][0]
    try:
        if online_master_sheet:
            data = _gs_read(lambda: online_master_sheet.get_all_records(), desc="online_master_sheet.get_all_records()")
        else:
            data = []
        _cache["online_master"] = (data, time.time())
        return data
    except Exception as e:
        print("⚠️ Error fetching online master list:", e)
        return _cache["online_master"][0] or []

def get_cached_attendance_rows():
    if _is_cache_fresh("attendance_rows"):
        return _cache["attendance_rows"][0]
    try:
        rows = _gs_read(lambda: attendance_sheet.get_all_records(), desc="attendance_sheet.get_all_records()")
        _cache["attendance_rows"] = (rows, time.time())
        return rows
    except Exception as e:
        print("⚠️ Error fetching attendance rows:", e)
        return _cache["attendance_rows"][0] or []

def get_cached_online_attendance_rows():
    if _is_cache_fresh("online_attendance_rows"):
        return _cache["online_attendance_rows"][0]
    try:
        if online_attendance_sheet:
            rows = _gs_read(lambda: online_attendance_sheet.get_all_records(), desc="online_attendance_sheet.get_all_records()")
        else:
            rows = []
        _cache["online_attendance_rows"] = (rows, time.time())
        return rows
    except Exception as e:
        print("⚠️ Error fetching online attendance rows:", e)
        return _cache["online_attendance_rows"][0] or []
# ---------------- Helpers ----------------
def get_today_date():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

def now_ts():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

def get_settings():
    s = get_cached_settings()
    return (s.get("DailyEasterEgg", "").strip(), s.get("StartTime", "00:00").strip(), s.get("EndTime", "23:59").strip())

def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def within_allowed_time():
    try:
        s = get_cached_settings()
        start_str = s.get("StartTime", "00:00").strip()
        end_str = s.get("EndTime", "23:59").strip()
        start_t = datetime.strptime(start_str, "%H:%M").time()
        end_t = datetime.strptime(end_str, "%H:%M").time()
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE)).time()
        except Exception:
            now_local = datetime.utcnow().time()
        if start_t <= end_t:
            ok = start_t <= now_local <= end_t
        else:
            ok = now_local >= start_t or now_local <= end_t
        if ok:
            return True
        return False, f"⏰ Attendance allowed only between {start_str} - {end_str}."
    except Exception as e:
        print("⚠️ Error checking allowed time:", e)
        return True

# Sheet utility helpers
def get_header_map(sheet):
    header = sheet.row_values(1)
    col_index = {name: idx+1 for idx, name in enumerate(header)}
    return header, col_index

def ensure_columns(sheet, columns):
    header, col_map = get_header_map(sheet)
    changed = False
    for col in columns:
        if col not in col_map:
            header.append(col)
            sheet.update_cell(1, len(header), col)
            changed = True
    if changed:
        # refresh map
        header, col_map = get_header_map(sheet)
    return col_map

def find_row_index_by_reg(sheet, reg_id):
    try:
        rows = sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("Reg ID", "")).strip() == str(reg_id):
                return i
    except Exception as e:
        print("find_row_index_by_reg error:", e)
    return None

def find_student_by_reg(sheet, reg_id):
    try:
        rows = sheet.get_all_records()
        for r in rows:
            if str(r.get("Reg ID", "")).strip() == str(reg_id):
                return r
    except Exception as e:
        print("find_student_by_reg error:", e)
    return None

def get_user_mode(uid):
    reg_id = str(uid)
    if online_master_sheet:
        r = find_student_by_reg(online_master_sheet, reg_id)
        if r:
            return "online"
    r = find_student_by_reg(master_sheet, reg_id)
    if r:
        return "offline"
    return None

def _invite_row(inv_link, group_id, user_id, kind, expire_at_str):
    return [inv_link, str(group_id), str(user_id), kind, "ACTIVE", now_ts(), expire_at_str or "", ""]

def invites_store(inv_link, group_id, user_id, kind, expire_at=None):
    try:
        invites_sheet.append_row(
            _invite_row(inv_link, group_id, user_id, kind, expire_at.strftime("%Y-%m-%d %H:%M:%S") if expire_at else ""),
            value_input_option='USER_ENTERED'
        )
    except Exception as e:
        print("invites_store error:", e)

def invites_find_by_link(link):
    try:
        rows = invites_sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("InviteLink","")).strip() == str(link).strip():
                return i, r
    except Exception as e:
        print("invites_find_by_link error:", e)
    return None, None

def invites_mark_used(row_idx):
    try:
        invites_sheet.update_cell(row_idx, 5, "USED")   # Status
        invites_sheet.update_cell(row_idx, 8, now_ts()) # UsedAt
    except Exception as e:
        print("invites_mark_used error:", e)

def invites_revoke(link):
    # Optional: you can revoke an invite link via the Bot API if you want.
    # Not strictly needed because we use join-requests + approval filter.
    pass

def create_one_time_invite_for(user_id, kind="normal"):
    """
    Creates a join-request invite link that only this user can actually get approved for.
    We also store it in the Invites sheet.
    """
    group_id = int(os.getenv("BATCH_GROUP_ID","0"))
    if not group_id:
        raise RuntimeError("BATCH_GROUP_ID missing")

    # Optional expiry
    mins = int(os.getenv("INVITE_EXPIRE_MIN","0") or "0")
    expire_dt = None
    if mins > 0:
        expire_dt = datetime.now(ZoneInfo(TIMEZONE)) + timedelta(minutes=mins)
        expire_unix = int(expire_dt.timestamp())
    else:
        expire_unix = None

    # Create invite link that requires approval
    # member_limit=1 keeps it single-use; creates_join_request=True prevents auto-join
    try:
        link_obj = bot.create_chat_invite_link(
            chat_id=group_id,
            name=f"{kind}-{user_id}-{int(time.time())}",
            expire_date=expire_unix,
            creates_join_request=True
        )
        inv_link = link_obj.invite_link
        invites_store(inv_link, group_id, user_id, kind, expire_dt)
        return inv_link
    except Exception as e:
        print("create_one_time_invite_for error:", e)
        raise
            


# ---------------- Daily reset ----------------
_last_reset_date = None
_reset_lock = threading.Lock()

def reset_attendance_if_new_day():
    global _last_reset_date
    today = get_today_date()
    with _reset_lock:
        if _last_reset_date == today:
            return False
        try:
            sheet_date = attendance_sheet.acell("C2").value
        except Exception:
            sheet_date = None
        if sheet_date == today:
            _last_reset_date = today
            return False
        print("🧹 Resetting attendance for new day...")
        attendance_sheet.clear()
        attendance_sheet.append_row(["Name", "Reg ID", "Date", "EasterEgg", "Timestamp", "Telegram ID"])
        if online_attendance_sheet:
            try:
                online_attendance_sheet.clear()
                online_attendance_sheet.append_row(["Name", "Reg ID", "Date", "EasterEgg", "Timestamp", "Telegram ID"])
            except Exception:
                pass
        with _queue_lock:
            marked_today_ids.clear()
            marked_today_online_ids.clear()
            write_queue.clear()
        invalidate_cache("attendance_rows")
        invalidate_cache("online_attendance_rows")
        _last_reset_date = today
        return True

# ---------------- Queue system (attendance row writes) ----------------
write_queue = deque()   # each element: ("offline"|"online", row_list)
_queue_lock = threading.Lock()
BATCH_SIZE = 60
BATCH_FLUSH_INTERVAL = 5

marked_today_ids = set()
marked_today_online_ids = set()

def load_marked_ids_from_sheet():
    try:
        today = get_today_date()
        rows = get_cached_attendance_rows()
        for r in rows:
            if str(r.get("Date")) == today:
                tid = str(r.get("Telegram ID", "")).strip()
                if tid:
                    marked_today_ids.add(tid)
        rows_online = get_cached_online_attendance_rows()
        for r in rows_online:
            if str(r.get("Date")) == today:
                tid = str(r.get("Telegram ID", "")).strip()
                if tid:
                    marked_today_online_ids.add(tid)
        print(f"Loaded {len(marked_today_ids)} offline and {len(marked_today_online_ids)} online marked Telegram IDs from sheet.")
    except Exception as e:
        print("Failed to load marked ids:", e)

def flush_queue_worker():
    while True:
        try:
            with _queue_lock:
                to_write = []
                while write_queue and len(to_write) < BATCH_SIZE:
                    to_write.append(write_queue.popleft())

            if to_write:
                offline_rows = [r for mode, r in to_write if mode == "offline"]
                online_rows = [r for mode, r in to_write if mode == "online"]

                if offline_rows:
                    try:
                        _gs_write(lambda: attendance_sheet.append_rows(offline_rows, value_input_option='USER_ENTERED'),
                                  desc=f"attendance_sheet.append_rows({len(offline_rows)} rows)")
                        invalidate_cache("attendance_rows")
                        print(f"✅ Flushed {len(offline_rows)} offline rows.")
                    except Exception as e:
                        print("⚠️ Offline write failed, requeuing:", e)
                        with _queue_lock:
                            for row in reversed([("offline", r) for r in offline_rows]):
                                write_queue.appendleft(row)

                if online_rows and online_attendance_sheet:
                    try:
                        _gs_write(lambda: online_attendance_sheet.append_rows(online_rows, value_input_option='USER_ENTERED'),
                                  desc=f"online_attendance_sheet.append_rows({len(online_rows)} rows)")
                        invalidate_cache("online_attendance_rows")
                        print(f"✅ Flushed {len(online_rows)} online rows.")
                    except Exception as e:
                        print("⚠️ Online write failed, requeuing:", e)
                        with _queue_lock:
                            for row in reversed([("online", r) for r in online_rows]):
                                write_queue.appendleft(row)

            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print("Batch worker error:", e)
            time.sleep(3)

threading.Thread(target=flush_queue_worker, daemon=True).start()
reset_attendance_if_new_day()
load_marked_ids_from_sheet()

# ---------------- Parent linking / queue helpers ----------------
def normalize_phone(number):
    t = number.strip().replace(" ", "")
    if t.startswith("+"):
        return t
    return "+91" + t

def ensure_parent_columns(sheet):
    # Add ParentPhone, ParentChatId, ParentLinked, ParentInvited
    return ensure_columns(sheet, ["ParentPhone","ParentChatId","ParentLinked","ParentInvited"])

def set_parent_info(sheet, reg_id, phone=None, chat_id=None, linked=None, invited=None):
    try:
        col_map = ensure_parent_columns(sheet)
        row_idx = find_row_index_by_reg(sheet, reg_id)
        if not row_idx:
            return False
        updates = []
        if phone is not None and "ParentPhone" in col_map:
            sheet.update_cell(row_idx, col_map["ParentPhone"], phone)
            updates.append("phone")
        if chat_id is not None and "ParentChatId" in col_map:
            sheet.update_cell(row_idx, col_map["ParentChatId"], str(chat_id))
            updates.append("chat")
        if linked is not None and "ParentLinked" in col_map:
            sheet.update_cell(row_idx, col_map["ParentLinked"], "Yes" if linked else "No")
            updates.append("linked")
        if invited is not None and "ParentInvited" in col_map:
            sheet.update_cell(row_idx, col_map["ParentInvited"], "Yes" if invited else "No")
            updates.append("invited")
        return True
    except Exception as e:
        print("set_parent_info error:", e)
        return False

def get_parent_info(sheet, reg_id):
    try:
        row = find_student_by_reg(sheet, reg_id)
        if not row:
            return {"ParentPhone":"", "ParentChatId":"", "ParentLinked":""}
        return {
            "ParentPhone": str(row.get("ParentPhone","")).strip(),
            "ParentChatId": str(row.get("ParentChatId","")).strip(),
            "ParentLinked": str(row.get("ParentLinked","")).strip(),
            "ParentInvited": str(row.get("ParentInvited","")).strip()
        }
    except Exception as e:
        print("get_parent_info error:", e)
        return {"ParentPhone":"", "ParentChatId":"", "ParentLinked":"", "ParentInvited":""}

def find_sheet_for_reg(reg_id):
    # prefer online sheet if found, else offline
    if online_master_sheet and find_row_index_by_reg(online_master_sheet, reg_id):
        return online_master_sheet, "online"
    if find_row_index_by_reg(master_sheet, reg_id):
        return master_sheet, "offline"
    return None, None

def is_onboarding_complete(reg_id: str):
    """
    A student is 'complete' when:
      • they exist in either MasterList (offline) or OnlineMasterList (online)
      • AND ParentLinked == 'Yes'
    """
    if online_master_sheet:
        row = find_student_by_reg(online_master_sheet, reg_id)
        if row:
            return str(row.get("ParentLinked","")).strip().lower() == "yes"
    row = find_student_by_reg(master_sheet, reg_id)
    if row:
        return str(row.get("ParentLinked","")).strip().lower() == "yes"
    return False

def parentqueue_enqueue(reg_id, date, mode, message):
    try:
        parent_queue_sheet.append_row([str(reg_id), date, mode, message, "PENDING", now_ts(), "", "0"], value_input_option='USER_ENTERED')
        print(f"📝 Queued parent notification for {reg_id} ({mode})")
    except Exception as e:
        print("parentqueue_enqueue error:", e)

# ---------------- Parent queue helpers ----------------
def parentqueue_list_pending():
    try:
        # use expected_headers to avoid gspread 'header row not unique' error
        rows = parent_queue_sheet.get_all_records(expected_headers=[
            "RegID","Date","Mode","Message","Status","CreatedAt","SentAt","Attempts"
        ])
        out = []
        for i, r in enumerate(rows, start=2):
            if str(r.get("Status","")).upper() == "PENDING":
                out.append((i, r))
        return out
    except Exception as e:
        print("parentqueue_list_pending error:", e)
        return []

def parentqueue_mark_sent(row_idx):
    try:
        parent_queue_sheet.update_cell(row_idx, 5, "SENT")      # Status
        parent_queue_sheet.update_cell(row_idx, 7, now_ts())    # SentAt
        attempts = parent_queue_sheet.cell(row_idx, 8).value or "0"
        parent_queue_sheet.update_cell(row_idx, 8, str(int(attempts)+1))
    except Exception as e:
        print("parentqueue_mark_sent error:", e)

def parentqueue_bump_attempt(row_idx):
    try:
        attempts = parent_queue_sheet.cell(row_idx, 8).value or "0"
        parent_queue_sheet.update_cell(row_idx, 8, str(int(attempts)+1))
    except Exception as e:
        print("parentqueue_bump_attempt error:", e)

def notify_parent_telegram(reg_id, student_name, date, mode):
    """
    If linked, send Telegram message; else queue for later.
    """
    sheet, m = find_sheet_for_reg(reg_id)
    if not sheet:
        return
    info = get_parent_info(sheet, reg_id)
    chatid = info.get("ParentChatId","").strip()
    linked = info.get("ParentLinked","").strip().lower() == "yes"

    msg = TPL_PARENT_ABSENT.format(student_name=student_name, reg_id=reg_id, date=date, mode=mode)

    if chatid and linked:
        try:
            safe_send_chat(chatid, msg)
            print(f"📨 Parent notified for {reg_id} ({mode}).")
        except Exception as e:
            print("notify_parent_telegram error:", e)
            # fallback to queue on failure
            parentqueue_enqueue(reg_id, date, mode, msg)
    else:
        parentqueue_enqueue(reg_id, date, mode, msg)

def deliver_pending_for_reg(reg_id):
    """
    When a parent links, deliver all pending notifications for this RegID immediately.
    """
    pending = parentqueue_list_pending()
    count = 0
    for row_idx, r in pending:
        if str(r.get("RegID","")).strip() == str(reg_id):
            # try to send now (should be linked now)
            sheet, mode = find_sheet_for_reg(reg_id)
            info = get_parent_info(sheet, reg_id) if sheet else {}
            chatid = info.get("ParentChatId","").strip()
            linked = info.get("ParentLinked","").strip().lower() == "yes"
            if chatid and linked:
                try:
                    safe_send_chat(chatid, r.get("Message",""))
                    parentqueue_mark_sent(row_idx)
                    count += 1
                except Exception as e:
                    print("deliver_pending_for_reg error:", e)
    if count:
        print(f"✅ Delivered {count} pending messages to parent of {reg_id}.")

# ---------------- Telegram handlers / state ----------------
pending_time_change = {}
registration_pending = {}
parent_pending = {}

def get_student_keyboard(uid=None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if uid:
        mode = get_user_mode(uid)
        if mode:
            kb.add(types.KeyboardButton("📍 Mark Attendance"))
            return kb
    kb.add(types.KeyboardButton("📝 Register"))
    return kb

def get_teacher_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Top 3", "📅 EOD Report")
    kb.row("🕒 Change Time", "🔄 Refresh Attendance")
    kb.row("📅 Bi-Weekly Report")
    kb.row("📅 Monthly Report", "📘 Course Summary")
    return kb

def get_location_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("Send Location 📍", request_location=True))
    return kb

# ---------------- Teacher buttons (fixed) ----------------
def _must_be_teacher(m):
    return str(m.from_user.id) == str(TEACHER_ID) or (ADMIN_ID and str(m.from_user.id) == str(ADMIN_ID))

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📊 Top 3")
def btn_top3(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    send_top3(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 EOD Report")
def btn_eod(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    send_report(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "🔄 Refresh Attendance")
def btn_refresh(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_refresh(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "🕒 Change Time")
def btn_change_time(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    safe_reply(m, "🕒 Please send the new Start Time (HH:MM):")
    pending_time_change[str(m.from_user.id)] = {"stage": "start"}

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 Bi-Weekly Report")
def btn_biweekly(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_biweekly(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 Monthly Report")
def btn_monthly(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_monthly(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📘 Course Summary")
def btn_course(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_course_summary(m)

@bot.message_handler(commands=['start'])
def start_cmd(msg):
    # Parse deep-link args (e.g., "/start parent_123")
    txt = (msg.text or "").strip()
    args = txt.split(" ", 1)[1].strip() if " " in txt else ""
    uid  = str(msg.from_user.id)

    # --- Parent linking flow ---
    if args.startswith("parent_"):
        reg_id = args.split("parent_", 1)[1].strip()
        sheet, mode = find_sheet_for_reg(reg_id)
        if not sheet:
            safe_reply(msg, "⚠️ Student not found for linking. Ask the student to share correct link.")
            return
        ensure_parent_columns(sheet)
        set_parent_info(sheet, reg_id, chat_id=msg.chat.id, linked=True)
        safe_reply(msg, TPL_PARENT_WELCOME)
        deliver_pending_for_reg(reg_id)

        # ✅ send the student's one-time group link immediately if onboarding is complete
        try:
            if is_onboarding_complete(reg_id):
                link = create_one_time_invite_for(int(reg_id), kind="student")
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("🔁 New link", callback_data=f"newlink:{reg_id}"))
                safe_send_chat(int(reg_id),
                    "✅ Onboarding complete!\n"
                    "Here is your one-time group invite (only you can use it):\n"
                    f"{link}",
                    reply_markup=kb
                )
                print(f"[ONBOARD] Sent one-time group link to student {reg_id}")
        except Exception as e:
            print("[ONBOARD] Failed to create/send student one-time link:", e)
        return

    # --- Recording student deep-link (immediate invite) ---
    if args.startswith("rec"):
        try:
            link = create_one_time_invite_for(int(uid), kind="recording")
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔁 New link", callback_data=f"newlink:{uid}"))
            # send message with inline button (same message will be edited when refreshing)
            safe_reply(msg,
                "🎧 Recording student detected.\n"
                "Tap this one-time link to join your class group (only you can use it):\n"
                f"{link}",
                reply_markup=kb
            )
        except Exception as e:
            safe_reply(msg, f"⚠️ Could not create your group link: {e}")
        return

    # --- Normal student deep-link (invite after onboarding completes) ---
    if args.startswith("norm"):
        # mark this user in-memory so after parent links we send the group link
        try:
            global _invite_after_onboarding
        except NameError:
            _invite_after_onboarding = set()
        _invite_after_onboarding.add(msg.from_user.id)
        # Fall through to the normal welcome/registration UI (no return)

    # --- Normal /start UI (no args) ---
    if uid == str(TEACHER_ID) or (ADMIN_ID and uid == str(ADMIN_ID)):
        kb = get_teacher_keyboard()
        safe_reply(msg, "👋 Hello Sir! Your panel:", reply_markup=kb)
        return

    kb = get_student_keyboard(msg.from_user.id)
    mode = get_user_mode(msg.from_user.id)
    if mode:
        safe_reply(
            msg,
            f"👋 Welcome back!\nYou are registered as **{mode.title()}**.\n\n"
            "Just tap **📍 Mark Attendance** each day.",
            reply_markup=kb
        )
    else:
        safe_reply(
            msg,
            "👋 Welcome!\n\n"
            "• Tap **📝 Register** once (bot will auto-save your Telegram ID as RegID and your Username).\n"
            "• Choose **Offline** or **Online**.\n"
            "• Then every day just tap **📍 Mark Attendance**.\n\n"
            "Offline will ask for location; Online marks immediately.",
            reply_markup=kb
        )
@bot.message_handler(func=lambda m: m.text == "📝 Register")
def register_init(msg):
    uid = msg.from_user.id
    registration_pending[uid] = True
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("🧑‍🏫 Offline"), types.KeyboardButton("💻 Online"))
    safe_reply(msg, "Choose your mode once:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🧑‍🏫 Offline", "💻 Online"])
def register_choose_mode(msg):
    uid = msg.from_user.id
    if uid not in registration_pending:
        return

    mode = "offline" if msg.text == "🧑‍🏫 Offline" else "online"
    name = (msg.from_user.first_name or "").strip() or f"Student_{uid}"
    username = (msg.from_user.username or "").strip()
    reg_id = str(uid)

    if mode == "offline":
        status = upsert_student(master_sheet, reg_id, name, username)
        ensure_parent_columns(master_sheet)
        # reset parent info
        set_parent_info(master_sheet, reg_id, phone="", chat_id="", linked=False, invited=False)
    else:
        if not online_master_sheet:
            safe_reply(msg, "⚠️ Online MasterList tab is not available. Ask admin to create 'OnlineMasterList'.")
            registration_pending.pop(uid, None)
            return
        status = upsert_student(online_master_sheet, reg_id, name, username)
        ensure_parent_columns(online_master_sheet)
        set_parent_info(online_master_sheet, reg_id, phone="", chat_id="", linked=False, invited=False)

    registration_pending.pop(uid, None)
    parent_pending[uid] = True

    link = f"https://t.me/{BOT_USERNAME}?start=parent_{reg_id}" if BOT_USERNAME else "(set BOT_USERNAME in .env)"
    safe_reply(
        msg,
        f"✅ Registered as **{mode.title()}**.\n"
        f"Your RegID = Telegram ID `{reg_id}`.\n\n"
        f"📎 Share this link with your parent to receive free Telegram updates:\n{link}\n\n"
        f"ℹ️ Note: After your parent clicks that link and completes the linking on *their* Telegram, we will automatically send *you* a one-time group invite link to join the class. You don't need to do anything more — just share the link with your parent and then wait for the confirmation message.\n\n"
        f"📱 Now please send your parent's phone number (with country code, or without for India +91)."
    )

@bot.message_handler(func=lambda m: m.from_user.id in parent_pending)
def register_parent_number(msg):
    uid = msg.from_user.id
    phone_raw = (msg.text or "").strip()
    if not phone_raw:
        safe_reply(msg, "⚠️ Please send a valid phone number.")
        return

    phone = normalize_phone(phone_raw)  # e.g. +9198..., +91 gets normalized inside helper too
    reg_id = str(uid)

    # Save phone into correct sheet
    sheet, mode = find_sheet_for_reg(reg_id)
    if not sheet:
        safe_reply(msg, "⚠️ Registration not found. Please try /start again.")
        parent_pending.pop(uid, None)
        return

    ensure_parent_columns(sheet)
    set_parent_info(sheet, reg_id, phone=phone)

    # --- DEBUG so we know why MSG91 may be skipped ---
    info = get_parent_info(sheet, reg_id)
    invited = str(info.get("ParentInvited","")).strip().lower() == "yes"
    linked  = str(info.get("ParentLinked","")).strip().lower() == "yes"
    template_name = os.getenv("MSG91_WHATSAPP_TEMPLATE_NAME", os.getenv("MSG91_WHATSAPP_TEMPLATE_ID_PARENT_INVITE","")).strip()
    namespace = os.getenv("MSG91_WHATSAPP_NAMESPACE","").strip()
    lang_code = os.getenv("MSG91_TEMPLATE_LANG","en_US").strip()

    print("[DEBUG] parent_number handler reached")
    print("[DEBUG] phone_normalized =", phone)
    print("[DEBUG] BOT_USERNAME =", BOT_USERNAME)
    print("[DEBUG] linked =", linked, "invited =", invited)
    print("[DEBUG] template_name =", template_name, "namespace =", namespace, "lang =", lang_code)

    # One-time WA invite via MSG91 (only if not linked already)
    if not linked and not invited and BOT_USERNAME and template_name and namespace:
        school_name = os.getenv("SCHOOL_NAME", "Our School")
        deep_link = f"https://t.me/{BOT_USERNAME}?start=parent_{reg_id}"
        vars_for_template = [school_name, deep_link]  # maps to {{1}}, {{2}} i.e., body_1, body_2
        print("[DEBUG] Will call MSG91 bulk ->", {"to": phone, "template": template_name, "vars": vars_for_template})

        ok = send_whatsapp_via_msg91(
            to_number=phone,
            template_id=template_name,      # we treat this as *name* in the bulk helper
            variables=vars_for_template,
            lang=lang_code,
            # media_url=None  # pass a public image URL here ONLY if your template header is Image
        )

        if ok:
            set_parent_info(sheet, reg_id, invited=True)
            print(f"✅ MSG91 WhatsApp invite sent to {phone} (reg {reg_id}).")
        else:
            print(f"⚠️ MSG91 WhatsApp invite failed for {phone} (reg {reg_id}). Will retry later.")
    else:
        reason = []
        if linked: reason.append("already linked")
        if invited: reason.append("already invited")
        if not BOT_USERNAME: reason.append("BOT_USERNAME missing")
        if not template_name: reason.append("template_name missing")
        if not namespace: reason.append("namespace missing")
        print("[DEBUG] Skipping MSG91 send because:", ", ".join(reason))

    # If the parent was already linked (ParentLinked == "Yes") at the time of saving the phone,
    # create & send the student's one-time group invite immediately.
    try:
        if linked:
            try:
                link = create_one_time_invite_for(int(reg_id), kind="student")
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("🔁 New link", callback_data=f"newlink:{reg_id}"))
                safe_send_chat(int(reg_id),
                    "✅ Onboarding complete!\n"
                    "Your parent is already linked — here is a one-time group invite just for you (only you can use it):\n"
                    f"{link}\n\n"
                    "Click that link to join the class group. 👋",
                    reply_markup=kb
                )
                print(f"[ONBOARD] Sent one-time group link to student {reg_id} (parent already linked at phone-save).")
            except Exception as e:
                print("[ONBOARD] Failed to create/send student one-time link (parent already linked):", e)
    except Exception:
        # defensive: do not block the normal flow if anything unexpected happens
        pass

    parent_pending.pop(uid, None)
    kb = get_student_keyboard(uid)
    # Inform the student clearly what happens next.
    safe_reply(
        msg,
        "✅ Parent number saved. Once your parent links their Telegram using the link you shared, we will send you a one-time invite link to join the class group and notify you when it's sent.",
        reply_markup=kb
    )
# ----- Registration core -----
def upsert_student(sheet, reg_id, name, username):
    try:
        rows = _gs_read(lambda: sheet.get_all_records())
        for i, r in enumerate(rows, start=2):
            if str(r.get("Reg ID","")).strip() == str(reg_id):
                # Update name if changed
                try:
                    if sheet.cell(i, 1).value != name:
                        sheet.update_cell(i, 1, name)
                except Exception:
                    pass
                return "updated"
        # Append new
        sheet.append_row([name, str(reg_id)], value_input_option='USER_ENTERED')
        return "inserted"
    except Exception as e:
        print("upsert_student error:", e)
        return "error"
# Mark attendance (one-tap)
@bot.message_handler(func=lambda m: m.text == "📍 Mark Attendance")
def mark_attendance_button(msg):
    uid = msg.from_user.id
    mode = get_user_mode(uid)
    if mode is None:
        safe_reply(msg, "⚠️ You are not registered.\nTap **📝 Register** first.", reply_markup=get_student_keyboard())
        return

    allowed = within_allowed_time()
    ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
    if not ok:
        safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
        return

    if mode == "online":
        reg_id = str(uid)
        student = find_student_by_reg(online_master_sheet, reg_id) if online_master_sheet else None
        student_name = (student or {}).get("Name", f"Student_{reg_id}")
        today = get_today_date()
        timestamp = now_ts()
        row = [student_name, reg_id, today, "-", timestamp, str(uid)]

        if str(uid) in marked_today_online_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today (online).")
            return

        with _queue_lock:
            write_queue.append(("online", row))
            marked_today_online_ids.add(str(uid))
        invalidate_cache("online_attendance_rows")
        safe_reply(msg, f"✅ Online attendance queued for {student_name} ({reg_id}) at {timestamp}")
    else:
        safe_reply(msg, "📍 Send your current location to complete offline attendance.", reply_markup=get_location_keyboard())

# Location handler for offline
@bot.message_handler(content_types=['location'])
def handle_location(msg):
    try:
        reset_attendance_if_new_day()
        uid = msg.from_user.id
        mode = get_user_mode(uid)
        if mode != "offline":
            safe_reply(msg, "⚠️ You are not registered as Offline.\nTap **📝 Register** and choose Offline.")
            return

        allowed = within_allowed_time()
        ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
        if not ok:
            safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
            return

        reg_id = str(uid)
        user_lat = msg.location.latitude
        user_lon = msg.location.longitude
        dist = distance_m(user_lat, user_lon, CLASS_LAT, CLASS_LON)
        if dist > RADIUS_METERS:
            safe_reply(msg, f"📍 Too far from class ({dist:.1f}m > {RADIUS_METERS}m).")
            return

        if str(uid) in marked_today_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today (offline).")
            return

        student = find_student_by_reg(master_sheet, reg_id)
        if not student:
            safe_reply(msg, "❌ You are not in the Offline Master List. Tap **📝 Register**.")
            return

        student_name = student.get("Name", f"Student_{reg_id}")
        timestamp = now_ts()
        row = [student_name, reg_id, get_today_date(), "-", timestamp, str(uid)]

        with _queue_lock:
            write_queue.append(("offline", row))
            marked_today_ids.add(str(uid))
        invalidate_cache("attendance_rows")
        safe_reply(msg, f"✅ Offline attendance queued for {student_name} ({reg_id}) at {timestamp}")
    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("Location handler error:", e)

@bot.message_handler(commands=['id'])
def get_ids(msg):
    try:
        chat_id = msg.chat.id
        thread_id = getattr(msg, "message_thread_id", None)
        print(f"[DEBUG]/id -> chat_id={chat_id}, thread_id={thread_id}, from={msg.from_user.id}")
        safe_reply(msg, f"🆔 Chat ID = `{chat_id}`\n🧵 Topic ID = `{thread_id}`")
    except Exception as e:
        print("get_ids error:", e)

# ---------------- /eod (offline + online + parent notify) ----------------
def generate_eod_and_notify():
    """Core EOD logic used by /eod and auto-EOD worker"""
    # Flush any pending queue rows first
    with _queue_lock:
        batch = []
        while write_queue:
            batch.append(write_queue.popleft())
    if batch:
        offline_rows = [r for mode, r in batch if mode == "offline"]
        online_rows = [r for mode, r in batch if mode == "online"]
        if offline_rows:
            attendance_sheet.append_rows(offline_rows, value_input_option='USER_ENTERED')
            invalidate_cache("attendance_rows")
        if online_rows and online_attendance_sheet:
            online_attendance_sheet.append_rows(online_rows, value_input_option='USER_ENTERED')
            invalidate_cache("online_attendance_rows")

    today = get_today_date()

    # --- OFFLINE ---
    attendance_rows = get_cached_attendance_rows()
    present_ids = {str(r.get("Reg ID", "")).strip() for r in attendance_rows}
    all_students = get_cached_master_list()
    absentees = [s for s in all_students if str(s.get("Reg ID", "")).strip() not in present_ids]
    offline_file = client.open_by_key(ABSENTEE_SHEET_ID)
    try:
        ws_off = offline_file.worksheet(f"{today}-offline")
    except gspread.exceptions.WorksheetNotFound:
        ws_off = offline_file.add_worksheet(title=f"{today}-offline", rows="500", cols="3")
        ws_off.update("A1:C1", [["Name", "Reg ID", "Date"]])
    ws_off.batch_clear(["A2:C"])
    if absentees:
        rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees]
        _gs_write(lambda: ws_off.append_rows(rows_to_write, value_input_option='USER_ENTERED'),
                  desc=f"ws_off.append_rows({len(rows_to_write)} rows for {today}-offline)")
        # Notify parents for OFFLINE
# --- PATCH START: AbsentStreak update + thresholded alerts (OFFLINE) ---
        # Ensure column to track absent streak exists
        try:
            ensure_columns(master_sheet, ["AbsentStreak"])
        except Exception:
            pass

        # thresholds at which we send explicit parent DM/alert
        STREAK_THRESHOLDS = {1,2,3,5,10}

        # Build a quick map of present ids for efficient update
        present_set = present_ids  # already computed above

        # Update streaks: increment for absentees, reset for present students
        try:
            for student_row in get_cached_master_list():
                rid = str(student_row.get("Reg ID","")).strip()
                row_idx = find_row_index_by_reg(master_sheet, rid)
                # read current streak (safe)
                cur = 0
                try:
                    cur_val = master_sheet.cell(row_idx, master_sheet.row_values(1).index("AbsentStreak")+1).value if row_idx else None
                    cur = int(cur_val) if cur_val and str(cur_val).isdigit() else 0
                except Exception:
                    cur = 0

                if rid not in present_set:
                    new_streak = cur + 1
                    if row_idx:
                        try:
                            master_sheet.update_cell(row_idx, master_sheet.row_values(1).index("AbsentStreak")+1, str(new_streak))
                        except Exception:
                            pass
                    # If this new_streak hits a threshold, send alert (queue if parent not linked)
                    if new_streak in STREAK_THRESHOLDS:
                        # per-threshold env var e.g. ABSENCE_3_MSG else fall back
                        env_key = f"ABSENCE_{new_streak}_MSG"
                        tpl = os.getenv(env_key) or os.getenv("ABSENCE_ALERT_MSG") or "⚠️ {student_name} missed {streak} classes (dates: {dates})."
                        # build short dates list (if you have abs_dates map)
                        dates = ", ".join(off_absdates.get(rid, [])) or today
                        try:
                            msg = tpl.format(student_name=student_row.get("Name",""), reg_id=rid, streak=new_streak, dates=dates)
                            # If parent linked -> direct DM, else queue
                            info = get_parent_info(master_sheet, rid)
                            chatid = info.get("ParentChatId","").strip()
                            linked = info.get("ParentLinked","").strip().lower() == "yes"
                            if chatid and linked:
                                safe_send_chat(chatid, msg)
                            else:
                                parentqueue_enqueue(rid, today, "offline", msg)
                        except Exception:
                            pass
                else:
                    # reset streak for present students
                    if cur != 0 and row_idx:
                        try:
                            master_sheet.update_cell(row_idx, master_sheet.row_values(1).index("AbsentStreak")+1, "0")
                        except Exception:
                            pass
        except Exception as e:
            print("⚠️ AbsentStreak offline update error:", e)

        for s in absentees:
            notify_parent_telegram(str(s.get("Reg ID","")), s.get("Name",""), today, "offline")

    # --- ONLINE ---
    online_rows = get_cached_online_attendance_rows()
    present_online_ids = {str(r.get("Reg ID", "")).strip() for r in online_rows}
    all_online_students = get_cached_online_master_list()
    absentees_online = [s for s in all_online_students if str(s.get("Reg ID", "")).strip() not in present_online_ids]

    online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
    try:
        ws_on = online_file.worksheet(f"{today}-online")
    except gspread.exceptions.WorksheetNotFound:
        ws_on = online_file.add_worksheet(title=f"{today}-online", rows="500", cols="3")
        ws_on.update("A1:C1", [["Name", "Reg ID", "Date"]])
    ws_on.batch_clear(["A2:C"])
    if absentees_online:
        rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees_online]
        _gs_write(lambda: ws_on.append_rows(rows_to_write, value_input_option='USER_ENTERED'),
                  desc=f"ws_on.append_rows({len(rows_to_write)} rows for {today}-online)")
        # Notify parents for ONLINE

# --- PATCH START: AbsentStreak update + thresholded alerts (ONLINE) ---
        try:
            ensure_columns(online_master_sheet or master_sheet, ["AbsentStreak"])
        except Exception:
            pass

        STREAK_THRESHOLDS = {1,2,3,5,10}
        present_set_online = present_online_ids

        try:
            for student_row in get_cached_online_master_list():
                rid = str(student_row.get("Reg ID","")).strip()
                row_idx = find_row_index_by_reg(online_master_sheet or master_sheet, rid)
                cur = 0
                try:
                    cur_val = (online_master_sheet or master_sheet).cell(row_idx, (online_master_sheet or master_sheet).row_values(1).index("AbsentStreak")+1).value if row_idx else None
                    cur = int(cur_val) if cur_val and str(cur_val).isdigit() else 0
                except Exception:
                    cur = 0

                if rid not in present_set_online:
                    new_streak = cur + 1
                    if row_idx:
                        try:
                            (online_master_sheet or master_sheet).update_cell(row_idx, (online_master_sheet or master_sheet).row_values(1).index("AbsentStreak")+1, str(new_streak))
                        except Exception:
                            pass
                    if new_streak in STREAK_THRESHOLDS:
                        env_key = f"ABSENCE_{new_streak}_MSG"
                        tpl = os.getenv(env_key) or os.getenv("ABSENCE_ALERT_MSG") or "⚠️ {student_name} missed {streak} classes (dates: {dates})."
                        dates = ", ".join(on_absdates.get(rid, [])) or today
                        try:
                            msg = tpl.format(student_name=student_row.get("Name",""), reg_id=rid, streak=new_streak, dates=dates)
                            info = get_parent_info(online_master_sheet or master_sheet, rid)
                            chatid = info.get("ParentChatId","").strip()
                            linked = info.get("ParentLinked","").strip().lower() == "yes"
                            if chatid and linked:
                                safe_send_chat(chatid, msg)
                            else:
                                parentqueue_enqueue(rid, today, "online", msg)
                        except Exception:
                            pass
                else:
                    if cur != 0 and row_idx:
                        try:
                            (online_master_sheet or master_sheet).update_cell(row_idx, (online_master_sheet or master_sheet).row_values(1).index("AbsentStreak")+1, "0")
                        except Exception:
                            pass
        except Exception as e:
            print("⚠️ AbsentStreak online update error:", e)

        for s in absentees_online:
            notify_parent_telegram(str(s.get("Reg ID","")), s.get("Name",""), today, "online")

    # after finishing absentee sheets + parent notifications
    off_abs = len(absentees)
    on_abs = len(absentees_online)
    off_present = len(present_ids)
    on_present = len(present_online_ids)

    public = (
        f"📊 Attendance Report for {today}\n\n"
        f"📍 Offline: ✅ {off_present} / ❌ {off_abs}\n"
        f"🌐 Online:  ✅ {on_present} / ❌ {on_abs}"
    )
    _post_public(public)   # <-- no links for the topic

            

    return off_abs, on_abs, off_present, on_present

@bot.message_handler(commands=['eod'])
def send_report(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        off_abs, on_abs, off_present, on_present = generate_eod_and_notify()
        today = get_today_date()
        offline_link = f"https://docs.google.com/spreadsheets/d/{ABSENTEE_SHEET_ID}/edit#gid=0"
        online_link = f"https://docs.google.com/spreadsheets/d/{ONLINE_ABSENTEE_SHEET_ID}/edit#gid=0"
        report = (
            f"📊 Attendance Report for {today}\n\n"
            f"📍 Offline: ✅ {off_present} / ❌ {off_abs}\n"
            f"🌐 Online:  ✅ {on_present} / ❌ {on_abs}"
        )
        safe_reply(message, f"{report}\n\n📄 Offline Absentees: {offline_link}\n🌐 Online Absentees: {online_link}")
        print(f"EOD generated for {today}. offline_absent={off_abs}, online_absent={on_abs}")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating report: {e}")
        print("EOD error:", e)

@bot.message_handler(commands=['biweekly'])
def manual_biweekly(message):
    uid = str(message.from_user.id)
    if uid != str(TEACHER_ID) and (not ADMIN_ID or uid != str(ADMIN_ID)):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        send_biweekly_report()  # <-- calls the same function your worker uses
        safe_reply(message, "📅 Bi-Weekly Report generated and shared.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating bi-weekly report: {e}")
        print("manual_biweekly error:", e)

@bot.message_handler(commands=['monthly'])
def manual_monthly(message):
    uid = str(message.from_user.id)
    if uid != str(TEACHER_ID) and (not ADMIN_ID or uid != str(ADMIN_ID)):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        send_monthly_report()
        safe_reply(message, "📅 Monthly Report generated and shared.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating monthly report: {e}")
        print("manual_monthly error:", e)


@bot.message_handler(commands=['course'])
def manual_course_summary(message):
    uid = str(message.from_user.id)
    if uid != str(TEACHER_ID) and (not ADMIN_ID or uid != str(ADMIN_ID)):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        send_course_summary_report()
        safe_reply(message, "📘 Course Summary report generated and shared.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating course summary: {e}")
        print("manual_course_summary error:", e)


# ---------------- /top3 (offline + online) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        print("⏱️ publish_top3_to_teacher_and_topic(): starting…")
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            if total_classes == 0:
                return f"⚠️ No {label.lower()} attendance history yet."

            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in tabs:
                absentees = _gs_read(lambda: ws.get_all_records())
                for a in absentees:
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1

            results = []
            for reg_id, data in stats.items():
                absent = data["Absent"]
                present = total_classes - absent
                percent = (present / total_classes) * 100 if total_classes else 0
                results.append((data["Name"], reg_id, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))

            msg = f"🏆 {label} Top Performers (out of {total_classes} classes):\n\n"
            rank = 1
            prev_percent = None
            group = []
            rank_emojis = {1: "🥇 Top 1", 2: "🥈 Top 2", 3: "🥉 Top 3"}
            for name, reg, present, absent, percent in results:
                if prev_percent is None or percent < prev_percent:
                    if rank > 3:
                        break
                    if group:
                        msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                        for g in group:
                            msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                        msg += "\n"
                        group = []
                    prev_percent = percent
                    rank += 1
                group.append((name, reg, present, absent, percent))

            if group and rank-1 <= 3:
                msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                for g in group:
                    msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                msg += "\n"

            return msg.strip()

        # OFFLINE
        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        offline_msg = build_top3(offline_tabs, get_cached_master_list(), len(offline_tabs), "Offline")

        # ONLINE
        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        online_msg = build_top3(online_tabs, get_cached_online_master_list(), len(online_tabs), "Online")

        safe_reply(message, offline_msg + "\n\n" + online_msg)
        _post_public(offline_msg + "\n\n" + online_msg)
    except Exception as e:
        print("publish_top3_to_teacher_and_topic error:",e)
        if ADMIN_ID:
            try:
                safe_send_chat(ADMIN_ID, f"⚠️ publish_top3_to_teacher_and_topic error: {e}")
            except Exception: pass
