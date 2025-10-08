# attendance_bot.py — merged Offline + Online version
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
ONLINE_SHEET_ID = os.getenv("ONLINE_SHEET_ID", SHEET_ID)
ONLINE_MASTER_TAB = os.getenv("ONLINE_MASTER_TAB", "OnlineMasterList")
ONLINE_ATTENDANCE_TAB = os.getenv("ONLINE_ATTENDANCE_TAB", "OnlineAttendance")
TEACHER_ID = os.getenv("TEACHER_ID")
TIMEZONE = os.getenv("TIMEZONE", "UTC")
CLASS_LAT = float(os.getenv("CLASS_LAT", 0))
CLASS_LON = float(os.getenv("CLASS_LON", 0))
RADIUS_METERS = float(os.getenv("RADIUS_METERS", 100))
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL", "")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set in environment.")
if not SHEET_ID or not SERVICE_ACCOUNT_JSON:
    raise SystemExit("SHEET_ID / SERVICE_ACCOUNT_JSON must be set.")

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

# Online tabs (same workbook, just different tabs)
try:
    online_attendance_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineAttendance")
    online_master_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineMasterList")
except Exception as e:
    print("⚠️ Online sheets access error (check tab names in Google Sheet):", e)
    online_attendance_sheet = None
    online_master_sheet = None

# ---------------- Simple cache (TTL = 60s) ----------------
CACHE_TTL = 60
_cache = {"settings": (None, 0), "master": (None, 0), "attendance_rows": (None, 0),
          "online_master": (None, 0), "online_attendance_rows": (None, 0)}

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

def get_cached_online_master_list():
    if _is_cache_fresh("online_master"):
        return _cache["online_master"][0]
    try:
        data = online_master_sheet.get_all_records()
        _cache["online_master"] = (data, time.time())
        return data
    except Exception as e:
        print("⚠️ Error fetching online master list:", e)
        return _cache["online_master"][0] or []

def get_cached_online_attendance_rows():
    if _is_cache_fresh("online_attendance_rows"):
        return _cache["online_attendance_rows"][0]
    try:
        rows = online_attendance_sheet.get_all_records()
        _cache["online_attendance_rows"] = (rows, time.time())
        return rows
    except Exception as e:
        print("⚠️ Error fetching online attendance rows:", e)
        return _cache["online_attendance_rows"][0] or []

# ---------------- Helpers ----------------
def get_today_date():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

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

# ---------------- Queue system ----------------
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
                            for row in reversed([( "offline", r) for r in offline_rows]):
                                write_queue.appendleft(row)

                if online_rows and online_attendance_sheet:
                    try:
                        online_attendance_sheet.append_rows(online_rows, value_input_option='USER_ENTERED')
                        invalidate_cache("online_attendance_rows")
                        print(f"✅ Flushed {len(online_rows)} online rows.")
                    except Exception as e:
                        print("⚠️ Online write failed, requeuing:", e)
                        with _queue_lock:
                            for row in reversed([( "online", r) for r in online_rows]):
                                write_queue.appendleft(row)

            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print("Batch worker error:", e)
            time.sleep(3)

threading.Thread(target=flush_queue_worker, daemon=True).start()
reset_attendance_if_new_day()
load_marked_ids_from_sheet()

# ---------------- Telegram handlers / state ----------------
user_pending = {}         # telegram_id -> {"mode": "offline"/"online", "reg_id": "..."}
pending_change = {}       # for teacher change egg
pending_time_change = {}

# Keyboards
def get_student_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🧑‍🏫 Offline"), types.KeyboardButton("💻 Online"))
    return kb

def get_teacher_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📍 Mark Attendance", "📊 Top 3")
    kb.row("✏️ Change Egg", "🕒 Change Time")
    kb.row("📅 EOD Report", "🔄 Refresh Attendance")
    return kb
# ---------------- Teacher menu button handler ----------------
@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text in [
    "📍 Mark Attendance", "📊 Top 3", "✏️ Change Egg",
    "🕒 Change Time", "📅 EOD Report", "🔄 Refresh Attendance"
])
def handle_teacher_buttons(msg):
    uid = str(msg.from_user.id)
    text = msg.text

    if uid != str(TEACHER_ID):
        safe_reply(msg, "❌ You are not authorized for this command.")
        return

    if text == "📍 Mark Attendance":
        safe_reply(msg, "Please send <EasterEgg> <RegID> to begin.")

    elif text == "📊 Top 3":
        send_top3(msg)

    elif text == "✏ Change Egg":
        safe_reply(msg, "✏ Please send the new Easter Egg for today:")
        pending_change[uid] = True

    elif text == "🕒 Change Time":
        safe_reply(msg, "🕒 Please send the new Start Time (HH:MM):")
        pending_time_change[uid] = {"stage": "start"}

    elif text == "📅 EOD Report":
        send_report(msg)

    elif text == "🔄 Refresh Attendance":
        manual_refresh(msg)

@bot.message_handler(commands=['start'])
def start_cmd(msg):
    uid = str(msg.from_user.id)
    if uid == str(TEACHER_ID):
        kb = get_teacher_keyboard()
        safe_reply(msg, "👋 Hello Sir! Your panel:", reply_markup=kb)
    else:
        kb = get_student_keyboard()
        safe_reply(msg, "👋 Tap to choose mode:\n🧑‍🏫 Offline = location-based\n💻 Online = EasterEgg only", reply_markup=kb)

# Mode selection handlers
@bot.message_handler(func=lambda m: m.text == "🧑‍🏫 Offline")
def set_offline_mode(msg):
    user_pending[msg.from_user.id] = {"mode": "offline"}
    safe_reply(msg, "📍 Offline selected. Send `<EasterEgg> <RegID>` then share your 📍 location to mark offline attendance.")

@bot.message_handler(func=lambda m: m.text == "💻 Online")
def set_online_mode(msg):
    user_pending[msg.from_user.id] = {"mode": "online"}
    safe_reply(msg, "💻 Online selected. Send `<EasterEgg> <RegID>` to mark online attendance (no location required).")

# Change egg/time handlers (teacher) — reuse your existing logic but using safe_reply
@bot.message_handler(commands=['change'])
def change_easter_egg(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    safe_reply(message, "✏️ Please send the new Easter Egg for today:")
    pending_change[str(message.from_user.id)] = True

@bot.message_handler(func=lambda m: str(m.from_user.id) in pending_change)
def set_new_easter_egg(message):
    try:
        new_egg = message.text.strip()
        if not new_egg:
            safe_reply(message, "⚠️ Invalid Easter Egg.")
            return
        settings_sheet.update_acell("A2", new_egg)
        invalidate_cache("settings")
        safe_reply(message, f"✅ Easter Egg updated to: *{new_egg}*")
    except Exception as e:
        safe_reply(message, f"⚠️ Error updating Easter Egg: {e}")
    finally:
        pending_change.pop(str(message.from_user.id), None)

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
        end = (start + timedelta(minutes=10)).strftime("%H:%M")
        settings_sheet.update_acell("B2", msg.text.strip())
        settings_sheet.update_acell("C2", end)
        invalidate_cache("settings")
        safe_reply(msg, f"✅ Time window updated:\nStart {msg.text.strip()} → End {end}")
    except Exception as e:
        safe_reply(msg, f"⚠ Error: {e}")
    finally:
        pending_time_change.pop(uid, None)

# Handle EasterEgg + RegID (works for both modes)
@bot.message_handler(func=lambda m:
    m.text is not None
    and not m.text.startswith('/')
    and str(m.from_user.id) not in pending_change   # <-- prevents hijacking "change egg"
    and str(m.from_user.id) not in pending_time_change  # <-- prevents hijacking "change time"
    )
def handle_easteregg(msg):
    try:
        reset_attendance_if_new_day()
        text = msg.text.strip()
        parts = text.split()
        if len(parts) != 2:
            safe_reply(msg, "❌ Invalid format. Use `<EasterEgg> <RegID>`")
            return

        easter, reg_id = parts
        daily_egg, _, _ = get_settings()
        allowed = within_allowed_time()
        if isinstance(allowed, tuple):
            ok, msg_text = allowed
        else:
            ok, msg_text = allowed, ""
        if not ok:
            safe_reply(msg, msg_text)
            return

        if easter.lower() != daily_egg.lower():
            safe_reply(msg, "❌ Wrong Easter Egg.")
            return

        # Determine mode (previous selection or default offline)
        pending = user_pending.get(msg.from_user.id) or {}
        mode = pending.get("mode", "offline")

        if mode == "online":
            today = get_today_date()
            timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

            # Match Reg ID against OnlineMasterList
            students = get_cached_online_master_list()
            student = next((s for s in students if str(s.get("Reg ID", "")).strip() == str(reg_id).strip()), None)

            if not student:
                safe_reply(msg, "❌ Invalid RegID. You are not in the Online Master List.")
                return

            student_name = student.get("Name", "Unknown")
            row = [student_name, reg_id, today, easter, timestamp, str(msg.from_user.id)]

            with _queue_lock:
                write_queue.append(("online", row))
                marked_today_online_ids.add(str(msg.from_user.id))

            invalidate_cache("online_attendance_rows")
            safe_reply(msg, f"✅ Online attendance queued for {student_name} ({reg_id}) at {timestamp}")

        else:
            # For offline, store reg_id and wait for location
            user_pending[msg.from_user.id] = {"mode": "offline", "reg_id": reg_id}
            safe_reply(msg, "✅ Verified — now share 📍 location for offline attendance.")

    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("EasterEgg handler error:", e)
# Location handler for offline finalization
@bot.message_handler(content_types=['location'])
def handle_location(msg):
    try:
        reset_attendance_if_new_day()
        uid = msg.from_user.id
        pending = user_pending.get(uid)
        if not pending or pending.get("mode") != "offline" or not pending.get("reg_id"):
            safe_reply(msg, "❌ Please send `<EasterEgg> <RegID>` first (and ensure Offline mode selected).")
            return

        allowed = within_allowed_time()
        ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
        if not ok:
            safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
            return

        reg_id = pending.get("reg_id")
        user_lat = msg.location.latitude
        user_lon = msg.location.longitude
        dist = distance_m(user_lat, user_lon, CLASS_LAT, CLASS_LON)
        if dist > RADIUS_METERS:
            safe_reply(msg, f"📍 Too far from class ({dist:.1f}m > {RADIUS_METERS}m).")
            user_pending.pop(uid, None)
            return

        if str(uid) in marked_today_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today (offline).")
            user_pending.pop(uid, None)
            return

        # Validate Reg ID in master list (cached)
        students = get_cached_master_list()
        student = next((s for s in students if str(s.get("Reg ID", "")).strip() == str(reg_id).strip()), None)
        if not student:
            safe_reply(msg, "❌ Invalid RegID. You are not in the Master List.")
            user_pending.pop(uid, None)
            return

        student_name = student.get("Name", "Unknown")
        timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        daily_egg = get_settings()[0]
        row = [student_name, reg_id, get_today_date(), daily_egg, timestamp, str(uid)]
        with _queue_lock:
            write_queue.append(("offline", row))
            marked_today_ids.add(str(uid))
        invalidate_cache("attendance_rows")
        safe_reply(msg, f"✅ Offline attendance queued for {student_name} ({reg_id}) at {timestamp}")
        user_pending.pop(uid, None)
    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("Location handler error:", e)

# ---------------- /eod (offline + online) ----------------
@bot.message_handler(commands=['eod'])
def send_report(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        # Flush any pending rows
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

        # --- ONLINE ---
        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_rows = get_cached_online_attendance_rows()
        present_online_ids = {str(r.get("Reg ID", "")).strip() for r in online_rows}
        all_online_students = get_cached_online_master_list()
        absentees_online = [s for s in all_online_students if str(s.get("Reg ID", "")).strip() not in present_online_ids]

        try:
            ws_on = online_file.worksheet(f"{today}-online")
        except gspread.exceptions.WorksheetNotFound:
            ws_on = online_file.add_worksheet(title=f"{today}-online", rows="500", cols="3")
            ws_on.update("A1:C1", [["Name", "Reg ID", "Date"]])
        ws_on.batch_clear(["A2:C"])
        if absentees_online:
            rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees_online]
            ws_on.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        # --- Final reply ---
        offline_link = f"https://docs.google.com/spreadsheets/d/{ABSENTEE_SHEET_ID}/edit#gid=0"
        online_link = f"https://docs.google.com/spreadsheets/d/{ONLINE_ABSENTEE_SHEET_ID}/edit#gid=0"

        report = (
            f"📊 Attendance Report for {today}\n\n"
            f"📍 Offline: ✅ {len(present_ids)} / ❌ {len(absentees)}\n"
            f"🌐 Online: ✅ {len(present_online_ids)} / ❌ {len(absentees_online)}"
        )
        safe_reply(message, f"{report}\n\n📄 Offline Absentees: {offline_link}\n🌐 Online Absentees: {online_link}")
        print(f"EOD generated for {today}. offline_absent={len(absentees)}, online_absent={len(absentees_online)}")
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
        # --- OFFLINE ---
        offline_file = client.open_by_key(ABSENTEE_SHEET_ID)
        offline_tabs = [ws for ws in offline_file.worksheets() if ws.title.endswith("-offline")]
        total_off = len(offline_tabs)
        if total_off == 0:
            off_msg = "⚠️ No offline attendance history yet."
        else:
            students = get_cached_master_list()
            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in offline_tabs:
                for a in ws.get_all_records():
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1
            results = []
            for rid, data in stats.items():
                absent = data["Absent"]
                present = total_off - absent
                percent = (present / total_off) * 100 if total_off else 0
                results.append((data["Name"], rid, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))
            off_msg = f"🏆 Offline Top Performers (out of {total_off} classes):\n\n"
            rank, prev_percent = 1, None
            for name, reg, pres, absn, pct in results:
                if prev_percent is None or pct < prev_percent:
                    if rank > 3: break
                    prev_percent = pct
                off_msg += f"{rank}. {name} ({reg}) - ✅ {pres}, ❌ {absn}, 📊 {pct:.1f}%\n"
                rank += 1

        # --- ONLINE ---
        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        total_on = len(online_tabs)
        if total_on == 0:
            on_msg = "⚠️ No online attendance history yet."
        else:
            students_on = get_cached_online_master_list()
            stats_on = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students_on}
            for ws in online_tabs:
                for a in ws.get_all_records():
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats_on:
                        stats_on[rid]["Absent"] += 1
            results_on = []
            for rid, data in stats_on.items():
                absent = data["Absent"]
                present = total_on - absent
                percent = (present / total_on) * 100 if total_on else 0
                results_on.append((data["Name"], rid, present, absent, percent))
            results_on.sort(key=lambda x: (-x[4], -x[2]))
            on_msg = f"🏆 Online Top Performers (out of {total_on} classes):\n\n"
            rank, prev_percent = 1, None
            for name, reg, pres, absn, pct in results_on:
                if prev_percent is None or pct < prev_percent:
                    if rank > 3: break
                    prev_percent = pct
                on_msg += f"{rank}. {name} ({reg}) - ✅ {pres}, ❌ {absn}, 📊 {pct:.1f}%\n"
                rank += 1

        safe_reply(message, off_msg + "\n\n" + on_msg)
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)

# ---------------- /refresh ----------------
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
    # Set webhook if provided (Render)
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            print(f"✅ Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            print("❌ Failed to set webhook:", e)

    # Start keep-alive pinger thread
    threading.Thread(target=keep_alive, daemon=True).start()

    # Ensure housekeeping
    reset_attendance_if_new_day()
    load_marked_ids_from_sheet()



    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
