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



# ---------------- MSG91 WhatsApp Helper ----------------
def send_whatsapp_via_msg91(to_number_e164: str, deep_link: str) -> bool:
    """
    Send a WhatsApp template message via MSG91 with a single variable ({{1}} = deep_link).
    to_number_e164: can be '+91xxxxxxxxxx' or '91xxxxxxxxxx' or 'xxxxxxxxxx'
    """
    if not (MSG91_AUTH_KEY and MSG91_SENDER_ID and MSG91_TEMPLATE_PARENT_INVITE):
        print("⚠️ MSG91 not configured (auth/sender/template).")
        return False

    # MSG91 expects numbers without '+'; include country code.
    num = to_number_e164.strip().replace(" ", "")
    if num.startswith("+"):
        num = num[1:]

    payload = {
        "integrated_number": str(MSG91_SENDER_ID),       # your approved WA business number
        "recipient_number":  str(num),                   # parent's number (no '+')
        "template_id":       str(MSG91_TEMPLATE_PARENT_INVITE),
        "variables":         [deep_link]                 # {{1}} = link
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authkey": MSG91_AUTH_KEY
    }

    try:
        r = requests.post(
            "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/",
            json=payload, headers=headers, timeout=20
        )
        ok = (200 <= r.status_code < 300) and ("success" in r.text.lower())
        print("MSG91 WA send:", r.status_code, r.text[:160])
        return ok
    except Exception as e:
        print("❌ MSG91 send error:", e)
        return False


# ---------------- Google Sheets Auth ----------------
try:
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    print("✅ Google credentials loaded.")
except Exception as e:
    print("❌ Error loading Google credentials:", e)
    raise

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
        s = settings_sheet.get_all_records()[0]
        _cache["settings"] = (s, time.time())
        return s
    except Exception as e:
        print("⚠️ Error fetching settings:", e)
        return _cache["settings"][0] or {}

def get_cached_master_list():
    if _is_cache_fresh("master"):
        return _cache["master"][0]
    try:
        data = master_sheet.get_all_records()
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
            data = online_master_sheet.get_all_records()
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
        rows = attendance_sheet.get_all_records()
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
            rows = online_attendance_sheet.get_all_records()
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
                        attendance_sheet.append_rows(offline_rows, value_input_option='USER_ENTERED')
                        invalidate_cache("attendance_rows")
                        print(f"✅ Flushed {len(offline_rows)} offline rows.")
                    except Exception as e:
                        print("⚠️ Offline write failed, requeuing:", e)
                        with _queue_lock:
                            for row in reversed([("offline", r) for r in offline_rows]):
                                write_queue.appendleft(row)

                if online_rows and online_attendance_sheet:
                    try:
                        online_attendance_sheet.append_rows(online_rows, value_input_option='USER_ENTERED')
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

def parentqueue_enqueue(reg_id, date, mode, message):
    try:
        parent_queue_sheet.append_row([str(reg_id), date, mode, message, "PENDING", now_ts(), "", "0"], value_input_option='USER_ENTERED')
        print(f"📝 Queued parent notification for {reg_id} ({mode})")
    except Exception as e:
        print("parentqueue_enqueue error:", e)

def parentqueue_list_pending():
    try:
        rows = parent_queue_sheet.get_all_records()
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
    return kb

def get_location_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("Send Location 📍", request_location=True))
    return kb

# ---------------- Teacher button handler ----------------
@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text in [
    "📊 Top 3", "📅 EOD Report", "🔄 Refresh Attendance", "🕒 Change Time"
])
def handle_teacher_buttons(msg):
    uid = str(msg.from_user.id)
    text = msg.text

    if uid != str(TEACHER_ID):
        safe_reply(msg, "❌ You are not authorized for this command.")
        return

    if text == "📊 Top 3":
        send_top3(msg)
    elif text == "📅 EOD Report":
        send_report(msg)
    elif text == "🔄 Refresh Attendance":
        manual_refresh(msg)
    elif text == "🕒 Change Time":
        safe_reply(msg, "🕒 Please send the new Start Time (HH:MM):")
        pending_time_change[uid] = {"stage": "start"}

# ----- Registration core -----
def upsert_student(sheet, reg_id, name, username):
    try:
        rows = sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("Reg ID","")).strip() == str(reg_id):
                # Update name if different
                if sheet.cell(i, 1).value != name:
                    sheet.update_cell(i, 1, name)
                return "updated"
        # Append new
        sheet.append_row([name, str(reg_id)], value_input_option='USER_ENTERED')
        return "inserted"
    except Exception as e:
        print("upsert_student error:", e)
        return "error"

@bot.message_handler(commands=['start'])
def start_cmd(msg):
    # deep-link for parent linking: /start parent_<regid>
    txt = (msg.text or "").strip()
    if " " in txt:
        _, args = txt.split(" ", 1)
    else:
        args = ""

    if args.startswith("parent_"):
        reg_id = args.split("parent_", 1)[1].strip()
        # Link this chat as parent for reg_id
        sheet, mode = find_sheet_for_reg(reg_id)
        if not sheet:
            safe_reply(msg, "⚠️ Student not found for linking. Ask the student to share correct link.")
            return
        ensure_parent_columns(sheet)
        set_parent_info(sheet, reg_id, chat_id=msg.chat.id, linked=True)
        safe_reply(msg, TPL_PARENT_WELCOME)
        deliver_pending_for_reg(reg_id)
        return

    # Normal start flow
    uid = str(msg.from_user.id)
    if uid == str(TEACHER_ID) or (ADMIN_ID and uid == str(ADMIN_ID)):
        kb = get_teacher_keyboard()
        safe_reply(msg, "👋 Hello Sir! Your panel:", reply_markup=kb)
    else:
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
        f"📱 Now please send your parent's phone number (with country code, or without for India +91)."
    )

@bot.message_handler(func=lambda m: m.from_user.id in parent_pending)
def register_parent_number(msg):
    uid = msg.from_user.id
    phone_raw = (msg.text or "").strip()
    if not phone_raw:
        safe_reply(msg, "⚠️ Please send a valid phone number.")
        return

    phone = normalize_phone(phone_raw)
    reg_id = str(uid)

    # Save phone into correct sheet
    sheet, mode = find_sheet_for_reg(reg_id)
    if not sheet:
        safe_reply(msg, "⚠️ Registration not found. Please try /start again.")
        parent_pending.pop(uid, None)
        return

    ensure_parent_columns(sheet)
    set_parent_info(sheet, reg_id, phone=phone)

        # One-time WA invite via MSG91 (only if not linked already)
    info = get_parent_info(sheet, reg_id)
    invited = info.get("ParentInvited","").lower() == "yes"
    linked  = info.get("ParentLinked","").lower() == "yes"

    if not linked and not invited and BOT_USERNAME:
        deep_link = f"https://t.me/{BOT_USERNAME}?start=parent_{reg_id}"
        ok = send_whatsapp_via_msg91(phone, deep_link)
        set_parent_info(sheet, reg_id, invited=True)
        if ok:
            print(f"✅ MSG91 WhatsApp invite sent to {phone} (reg {reg_id}).")
        else:
            print(f"⚠️ MSG91 WhatsApp invite failed for {phone} (reg {reg_id}).")

    parent_pending.pop(uid, None)
    kb = get_student_keyboard(uid)
    safe_reply(msg, "✅ Parent number saved. From now, parent will receive absence updates once they join Telegram.", reply_markup=kb)


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
        ws_off.append_rows(rows_to_write, value_input_option='USER_ENTERED')
        # Notify parents for OFFLINE
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
        ws_on.append_rows(rows_to_write, value_input_option='USER_ENTERED')
        # Notify parents for ONLINE
        for s in absentees_online:
            notify_parent_telegram(str(s.get("Reg ID","")), s.get("Name",""), today, "online")

    return len(absentees), len(absentees_online), len(present_ids), len(present_online_ids)

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

# ---------------- /top3 (offline + online) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            if total_classes == 0:
                return f"⚠️ No {label.lower()} attendance history yet."

            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in tabs:
                absentees = ws.get_all_records()
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
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)

# ---------------- Teacher commands ----------------
@bot.message_handler(commands=['changetime'])
def changetime_cmd(msg):
    if str(msg.from_user.id) != str(TEACHER_ID):
        safe_reply(msg, "❌ Unauthorized.")
        return
    safe_reply(msg, "🕒 Send new Start Time (HH:MM):")
    pending_time_change[str(msg.from_user.id)] = {"stage": "start"}

@bot.message_handler(func=lambda m: str(m.from_user.id) in pending_time_change)
def update_time(msg):
    uid = str(msg.from_user.id)
    try:
        start = datetime.strptime(msg.text.strip(), "%H:%M")
        end = (start + timedelta(hours=4)).strftime("%H:%M")
        settings_sheet.update_acell("B2", msg.text.strip())
        settings_sheet.update_acell("C2", end)
        invalidate_cache("settings")
        safe_reply(msg, f"✅ Time window updated:\nStart {msg.text.strip()} → End {end}")
    except Exception as e:
        safe_reply(msg, f"⚠ Error: {e}")
    finally:
        pending_time_change.pop(uid, None)

@bot.message_handler(commands=['refresh'])
def manual_refresh(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        attendance_sheet.clear()
        attendance_sheet.append_row(["Name", "Reg ID", "Date", "EasterEgg", "Timestamp", "Telegram ID"])
        if online_attendance_sheet:
            online_attendance_sheet.clear()
            online_attendance_sheet.append_row(["Name", "Reg ID", "Date", "EasterEgg", "Timestamp", "Telegram ID"])
        with _queue_lock:
            write_queue.clear()
            marked_today_ids.clear()
            marked_today_online_ids.clear()
        invalidate_cache()
        safe_reply(message, "🔄 Attendance sheets have been manually refreshed successfully.")
        print("🧹 Manual refresh triggered by teacher.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error during manual refresh: {e}")
        print("Manual refresh error:", e)

# ---------------- Background workers ----------------
def auto_eod_worker():
    """Run every 2 minutes; if now > EndTime+2h and today's EOD not done, run EOD."""
    while True:
        try:
            s = get_cached_settings()
            end_str = s.get("EndTime", "23:59").strip()
            today = get_today_date()

            # parse today's local end time
            try:
                end_dt = datetime.strptime(today + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = datetime.now(ZoneInfo(TIMEZONE))

            if datetime.now(ZoneInfo(TIMEZONE)) >= (end_dt + timedelta(hours=2)):
                # check if tabs exist
                off_file = client.open_by_key(ABSENTEE_SHEET_ID)
                on_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
                off_done = any(ws.title == f"{today}-offline" for ws in off_file.worksheets())
                on_done  = any(ws.title == f"{today}-online"  for ws in on_file.worksheets())
                if not (off_done and on_done):
                    print("⏱️ Auto EOD running...")
                    generate_eod_and_notify()
            time.sleep(120)
        except Exception as e:
            print("auto_eod_worker error:", e)
            time.sleep(180)

def parent_queue_retry_worker():
    """Try to deliver pending parent notifications once a day."""
    while True:
        try:
            pending = parentqueue_list_pending()
            if not pending:
                time.sleep(3600*6)  # sleep 6h if none
                continue

            # For each pending, if parent linked now -> send
            for row_idx, r in pending:
                reg_id = str(r.get("RegID","")).strip()
                sheet, mode = find_sheet_for_reg(reg_id)
                info = get_parent_info(sheet, reg_id) if sheet else {}
                chatid = info.get("ParentChatId","").strip()
                linked = info.get("ParentLinked","").strip().lower() == "yes"
                if chatid and linked:
                    try:
                        safe_send_chat(chatid, r.get("Message",""))
                        parentqueue_mark_sent(row_idx)
                    except Exception as e:
                        print("parent_queue_retry send error:", e)
                        parentqueue_bump_attempt(row_idx)
                else:
                    parentqueue_bump_attempt(row_idx)

            time.sleep(3600*24)  # 24 hours
        except Exception as e:
            print("parent_queue_retry_worker error:", e)
            time.sleep(3600*6)

def weekly_summary_worker():
    while True:
        try:
            now = datetime.now(ZoneInfo(TIMEZONE))
            if now.weekday() == 6 and now.hour == 9 and now.minute < 5:  # Sunday ~09:00
                off_list = master_sheet.get_all_records()
                on_list = online_master_sheet.get_all_records() if online_master_sheet else []

                off_total = len(off_list)
                on_total = len(on_list)
                off_linked = sum(1 for r in off_list if str(r.get("ParentChatId","")).strip())
                on_linked  = sum(1 for r in on_list if str(r.get("ParentChatId","")).strip())

                msg = TPL_FACULTY_WEEKLY.format(
                    off_linked=off_linked, off_total=off_total,
                    on_linked=on_linked, on_total=on_total
                )
                if TEACHER_ID:
                    safe_send_chat(TEACHER_ID, msg)
            time.sleep(300)
        except Exception as e:
            print("Weekly summary error:", e)
            time.sleep(600)

threading.Thread(target=auto_eod_worker, daemon=True).start()
threading.Thread(target=parent_queue_retry_worker, daemon=True).start()
threading.Thread(target=weekly_summary_worker, daemon=True).start()

# ---------------- Flask server (Render) ----------------
app = Flask(__name__)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", f"https://{RENDER_URL}/{BOT_TOKEN}" if RENDER_URL else "")

@app.route('/', methods=['GET'])
def home():
    return "✅ Attendance Bot (Render) — live", 200




@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.data.decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("⚠️ Webhook error:", e)
        return "Error", 500

def keep_alive():
    if not RENDER_URL and not KEEP_ALIVE_URL:
        print("⚠️ No keep-alive configured; skipping pinger.")
        return
    url_to_ping = KEEP_ALIVE_URL or f"https://{RENDER_URL}/"
    while True:
        try:
            requests.get(url_to_ping, timeout=10)
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
            print("🔁 Keep-alive ping sent.")
        except Exception as e:
            print("⚠️ Keep-alive ping failed:", e)
        time.sleep(300)

# ---------------- Start ----------------
if __name__ == "__main__":
    print("🤖 Bot starting...")
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            print(f"✅ Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            print("❌ Failed to set webhook:", e)

    threading.Thread(target=keep_alive, daemon=True).start()
    reset_attendance_if_new_day()
    load_marked_ids_from_sheet()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
