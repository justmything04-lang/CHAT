
# attendance_bot.py  (final full version) — with caching (1 minute) and safe Telegram sends
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

# ---------------- Load env (Render uses env vars) ----------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
ABSENTEE_SHEET_ID = os.getenv("ABSENTEE_SHEET_ID")
TEACHER_ID = os.getenv("TEACHER_ID")
TIMEZONE = os.getenv("TIMEZONE", "UTC")
CLASS_LAT = float(os.getenv("CLASS_LAT", 0))
CLASS_LON = float(os.getenv("CLASS_LON", 0))
RADIUS_METERS = float(os.getenv("RADIUS_METERS", 100))
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL", "")  # set your Render URL in env

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set in environment.")
if not SHEET_ID or not ABSENTEE_SHEET_ID or not SERVICE_ACCOUNT_JSON:
    raise SystemExit("SHEET_ID / ABSENTEE_SHEET_ID / SERVICE_ACCOUNT_JSON must be set.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ---------------- Safe Telegram send helpers ----------------
# Telegram message limit is ~4096 characters. We'll safely truncate long messages.
TELEGRAM_TEXT_LIMIT = 3900  # leave some buffer

def _truncate_text(text):
    if not isinstance(text, str):
        return text
    if len(text) <= TELEGRAM_TEXT_LIMIT:
        return text
    # keep head + tail for readability
    head = text[:1800]
    tail = text[-1800:]
    return head + "\n\n...[truncated]...\n\n" + tail

def safe_reply(message_obj, text, **kwargs):
    """Reply to a message object, but handle Telegram API errors gracefully."""
    try:
        safe_text = _truncate_text(text)
        return bot.reply_to(message_obj, safe_text, **kwargs)
    except Exception as e:
        # If reply_to fails (e.g., chat not found during stress tests), try send_message by chat id
        try:
            chat_id = getattr(message_obj, "chat", {}).get("id", None) or getattr(message_obj.from_user, "id", None)
            if chat_id:
                safe_text = _truncate_text(text)
                return bot.send_message(chat_id, safe_text, **kwargs)
        except Exception as e2:
            print("⚠️ safe_reply failed:", e, "|| fallback failed:", e2)
        print("⚠️ safe_reply error:", e)
        return None

def safe_send_chat(chat_id, text, **kwargs):
    """Send a message to a chat_id safely."""
    try:
        safe_text = _truncate_text(text)
        return bot.send_message(chat_id, safe_text, **kwargs)
    except Exception as e:
        print("⚠️ safe_send_chat error:", e)
        return None

# ---------------- Custom Keyboards ----------------
def get_student_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add(types.KeyboardButton("📍 Mark Attendance"))
    return markup

def get_teacher_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.row("📍 Mark Attendance", "📊 Top 3")
    markup.row("✏️ Change Egg", "🕒 Change Time")
    markup.row("📅 EOD Report", "🔄 Refresh Attendance")
    return markup

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

# ---------------- Sheet Access Helpers ----------------
def open_sheet_with_retry(sheet_name, max_retries=5, delay=3):
    last_exc = None
    for attempt in range(max_retries):
        try:
            return client.open_by_key(SHEET_ID).worksheet(sheet_name)
        except Exception as e:
            last_exc = e
            print(f"Attempt {attempt+1} to open {sheet_name} failed: {e}")
            time.sleep(delay)
    raise last_exc

attendance_sheet = open_sheet_with_retry("Attendance")
master_sheet = open_sheet_with_retry("MasterList")
settings_sheet = open_sheet_with_retry("Settings")

# ---------------- Simple in-memory cache (TTL = 60s) ----------------
CACHE_TTL = 60  # seconds (user chose 1 minute)
_cache = {
    "settings": (None, 0),  # (value, timestamp)
    "master": (None, 0),
    "attendance_rows": (None, 0),
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
        # print("🟡 Using cached Settings")
        return _cache["settings"][0]
    try:
        s = settings_sheet.get_all_records()[0]
        _cache["settings"] = (s, time.time())
        # print("🟢 Fetched Settings from Sheets")
        return s
    except Exception as e:
        print("⚠️ Error fetching settings from Google Sheets:", e)
        # fallback to cached even if stale
        return _cache["settings"][0] or {}

def get_cached_master_list():
    if _is_cache_fresh("master"):
        # print("🟡 Using cached MasterList")
        return _cache["master"][0]
    try:
        data = master_sheet.get_all_records()
        _cache["master"] = (data, time.time())
        # print("🟢 Fetched MasterList from Sheets")
        return data
    except Exception as e:
        print("⚠️ Error fetching master list:", e)
        return _cache["master"][0] or []

def get_cached_attendance_rows():
    if _is_cache_fresh("attendance_rows"):
        # print("🟡 Using cached Attendance rows")
        return _cache["attendance_rows"][0]
    try:
        rows = attendance_sheet.get_all_records()
        _cache["attendance_rows"] = (rows, time.time())
        # print("🟢 Fetched Attendance rows from Sheets")
        return rows
    except Exception as e:
        print("⚠️ Error fetching attendance rows:", e)
        return _cache["attendance_rows"][0] or []

# ---------------- Helper Functions ----------------
def get_today_date():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

def get_settings():
    s = get_cached_settings()
    # return (DailyEasterEgg, StartTime, EndTime)
    return (
        s.get("DailyEasterEgg", "").strip(),
        s.get("StartTime", "00:00").strip(),
        s.get("EndTime", "23:59").strip(),
    )

def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def within_allowed_time():
    """Return True if now (in TIMEZONE) is between StartTime and EndTime.
       On error it returns True (fails open). Otherwise returns True or (False, message)."""
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

# ---------------- Daily Reset ----------------
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
        with _queue_lock:
            marked_today_ids.clear()
            write_queue.clear()
        invalidate_cache("attendance_rows")
        _last_reset_date = today
        return True

# ---------------- Queue System ----------------
write_queue = deque()
_queue_lock = threading.Lock()
BATCH_SIZE = 60
BATCH_FLUSH_INTERVAL = 5
marked_today_ids = set()

def load_marked_ids_from_sheet():
    try:
        today = get_today_date()
        rows = get_cached_attendance_rows()
        for r in rows:
            if str(r.get("Date")) == today:
                tid = str(r.get("Telegram ID", "")).strip()
                if tid:
                    marked_today_ids.add(tid)
        print(f"Loaded {len(marked_today_ids)} marked Telegram IDs from sheet.")
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
                try:
                    attendance_sheet.append_rows(to_write, value_input_option='USER_ENTERED')
                    # Invalidate attendance cache after successful write
                    invalidate_cache("attendance_rows")
                    print(f"✅ Flushed {len(to_write)} rows.")
                except Exception as e:
                    print("⚠️ Write failed, requeuing:", e)
                    with _queue_lock:
                        for row in reversed(to_write):
                            write_queue.appendleft(row)
            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print("Batch worker error:", e)
            time.sleep(3)

# Start batch worker thread
threading.Thread(target=flush_queue_worker, daemon=True).start()
# Initial reset and load
reset_attendance_if_new_day()
load_marked_ids_from_sheet()

# ---------------- Telegram Handlers / State ----------------
user_pending = {}         # telegram_id -> reg_id waiting for location
pending_change = {}       # teacher -> waiting to send new egg
pending_time_change = {}  # teacher -> {"stage": "start"/"end", "start": "HH:MM"}

@bot.message_handler(commands=['start'])
def send_welcome(msg):
    user_id = str(msg.from_user.id)
    if user_id == str(TEACHER_ID):
        markup = get_teacher_keyboard()
        safe_reply(msg, "👋 Hello Sir! Here are your admin controls:", reply_markup=markup)
    else:
        markup = get_student_keyboard()
        safe_reply(
            msg,
            "👋 Hello! Tap the button below to mark attendance.\n\n"
            "1️⃣ Enter `<EasterEgg> <RegID>`\n"
            "2️⃣ Then share your 📍 location to complete attendance.",
            reply_markup=markup
        )

# ---------------- Change Easter Egg (teacher) ----------------
@bot.message_handler(commands=['change'])
def change_easter_egg(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized. Only the teacher can change the Easter Egg.")
        return
    safe_reply(message, "✏️ Please send the new Easter Egg for today:")
    pending_change[str(message.from_user.id)] = True

@bot.message_handler(func=lambda m: str(m.from_user.id) in pending_change)
def set_new_easter_egg(message):
    try:
        new_egg = message.text.strip()
        if not new_egg:
            safe_reply(message, "⚠️ Invalid Easter Egg. Try again.")
            return
        # Update sheet: assume DailyEasterEgg is cell A2
        settings_sheet.update_acell("A2", new_egg)
        # invalidate settings cache
        invalidate_cache("settings")
        safe_reply(message, f"✅ Easter Egg updated to: *{new_egg}*")
    except Exception as e:
        safe_reply(message, f"⚠️ Error updating Easter Egg: {e}")
    finally:
        pending_change.pop(str(message.from_user.id), None)

# ---------------- Change Time (teacher) ----------------
@bot.message_handler(commands=['changetime'])
def change_time_command(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized. Only the teacher can change timings.")
        return
    safe_reply(message, "🕒 Please send the new *Start Time* in 24-hour format (HH:MM):")
    pending_time_change[str(message.from_user.id)] = {"stage": "start"}

@bot.message_handler(func=lambda m: str(m.from_user.id) in pending_time_change)
def handle_time_change_auto(message):
    uid = str(message.from_user.id)
    try:
        new_start = message.text.strip()
        # Validate time format
        start_dt = datetime.strptime(new_start, "%H:%M")
        # Add 10 minutes
        end_dt = (start_dt + timedelta(minutes=10)).time()
        end_str = end_dt.strftime("%H:%M")

        # Update both times in the sheet
        settings_sheet.update_acell("B2", new_start)
        settings_sheet.update_acell("C2", end_str)
        invalidate_cache("settings")

        safe_reply(
            message,
            f"✅ Attendance window updated:\n"
            f"Start ⏰ {new_start}\n"
            f"End ⏰ {end_str} (auto +10 min)"
        )

        # Clean up
        pending_time_change.pop(uid, None)

    except Exception as e:
        safe_reply(message, f"⚠️ Error updating times: {e}")
        pending_time_change.pop(uid, None)

# ---------------- Button clicks handler ----------------
@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text in [
    "📍 Mark Attendance", "📊 Top 3", "✏️ Change Egg",
    "🕒 Change Time", "📅 EOD Report", "🔄 Refresh Attendance"
])
def handle_button_click(msg):
    uid = str(msg.from_user.id)
    text = msg.text
    if text == "📍 Mark Attendance":
        safe_reply(msg, "Please send your `<EasterEgg> <RegID>` to begin.")
    elif text == "📊 Top 3" and uid == str(TEACHER_ID):
        send_top3(msg)
    elif text == "✏️ Change Egg" and uid == str(TEACHER_ID):
        change_easter_egg(msg)
    elif text == "🕒 Change Time" and uid == str(TEACHER_ID):
        change_time_command(msg)
    elif text == "📅 EOD Report" and uid == str(TEACHER_ID):
        send_report(msg)
    elif text == "🔄 Refresh Attendance" and uid == str(TEACHER_ID):
        manual_refresh(msg)
    else:
        safe_reply(msg, "❌ You are not authorized for this command.")

# ---------------- Attendance (EasterEgg + RegID) ----------------
@bot.message_handler(func=lambda m: m.text is not None and not m.text.startswith('/') and
                     str(m.from_user.id) not in pending_change and
                     str(m.from_user.id) not in pending_time_change)
def handle_easteregg(msg):
    try:
        reset_attendance_if_new_day()
        text = msg.text.strip()
        parts = text.split()
        if len(parts) != 2:
            safe_reply(msg, "❌ Invalid format. Use `<EasterEgg> <RegID>`")
            return

        easter, reg_id = parts
        daily_egg, start_time, end_time = get_settings()

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

        user_pending[msg.from_user.id] = reg_id
        safe_reply(msg, "✅ Verified — now share 📍 location.")
    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("EasterEgg handler error:", e)

# ---------------- Location handler (finalize attendance) ----------------
@bot.message_handler(content_types=['location'])
def handle_location(msg):
    try:
        reset_attendance_if_new_day()
        uid = msg.from_user.id
        if uid not in user_pending:
            safe_reply(msg, "❌ Please send your Easter Egg and RegID first.")
            return

        allowed = within_allowed_time()
        ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
        if not ok:
            safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
            return

        reg_id = user_pending.get(uid)
        user_lat = msg.location.latitude
        user_lon = msg.location.longitude
        dist = distance_m(user_lat, user_lon, CLASS_LAT, CLASS_LON)
        if dist > RADIUS_METERS:
            safe_reply(msg, f"📍 Too far from class ({dist:.1f}m > {RADIUS_METERS}m).")
            del user_pending[uid]
            return

        today = get_today_date()
        if str(uid) in marked_today_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today.")
            del user_pending[uid]
            return

        # Validate Reg ID is in master sheet (use cached master list)
        try:
            students = get_cached_master_list()
            student = next((s for s in students if str(s.get("Reg ID", "")).strip() == str(reg_id).strip()), None)
        except Exception:
            student = None

        if not student:
            safe_reply(msg, "❌ Invalid RegID. You are not in the Master List.")
            del user_pending[uid]
            return

        student_name = student.get("Name", "Unknown")
        timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        daily_egg = get_settings()[0]
        row = [student_name, reg_id, today, daily_egg, timestamp, str(uid)]

        with _queue_lock:
            write_queue.append(row)
            marked_today_ids.add(str(uid))

        # attendance cache will be invalidated when flush_queue_worker writes successfully
        safe_reply(msg, f"✅ Attendance queued for {student_name} ({reg_id}) at {timestamp}")
        del user_pending[uid]
    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("Location handler error:", e)

# ---------------- /eod (end of day report) ----------------
@bot.message_handler(commands=['eod'])
def send_report(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return

    try:
        # Flush pending queue immediately to ensure latest attendance is written
        with _queue_lock:
            batch = []
            while write_queue:
                batch.append(write_queue.popleft())
        if batch:
            attendance_sheet.append_rows(batch, value_input_option='USER_ENTERED')
            invalidate_cache("attendance_rows")

        attendance_rows = get_cached_attendance_rows()
        present_ids = {str(r.get("Reg ID", "")).strip() for r in attendance_rows}
        all_students = get_cached_master_list()
        absentees = [s for s in all_students if str(s.get("Reg ID", "")).strip() not in present_ids]
        today = get_today_date()

        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        # Get or create worksheet for today
        try:
            absentee_ws = absentee_file.worksheet(today)
        except gspread.exceptions.WorksheetNotFound:
            absentee_ws = absentee_file.add_worksheet(title=today, rows="500", cols="3")
            absentee_ws.update("A1:C1", [["Name", "Reg ID", "Date"]])

        # Clear previous entries before writing updated absentees (to avoid duplicates)
        existing_data = absentee_ws.get_all_records()
        if existing_data:
            # Clear A2:C (keeps header)
            absentee_ws.batch_clear(["A2:C"])

        # Write only *current* absentees
        if absentees:
            rows_to_write = [[s.get("Name", ""), s.get("Reg ID", ""), today] for s in absentees]
            absentee_ws.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        # Build summary message
        report = f"📊 Attendance Report for {today}\n✅ Present: {len(present_ids)}\n❌ Absent: {len(absentees)}"
        sheet_link = f"https://docs.google.com/spreadsheets/d/{ABSENTEE_SHEET_ID}/edit#gid=0"
        safe_reply(message, f"{report}\n\n📄 Absentee Sheet: {sheet_link}")

        print(f"EOD generated for {today}. {len(absentees)} absentees updated.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating report: {e}")
        print("EOD error:", e)

# ---------------- /top3 (grouped version) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return

    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)
        all_tabs = absentee_file.worksheets()
        total_classes = len(all_tabs)
        if total_classes == 0:
            safe_reply(message, "⚠️ No attendance history yet.")
            return

        all_students = get_cached_master_list()
        stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in all_students}

        # Count absences for each student
        for ws in all_tabs:
            absentees = ws.get_all_records()
            for a in absentees:
                rid = str(a.get("Reg ID", ""))
                if rid in stats:
                    stats[rid]["Absent"] += 1

        # Calculate performance
        results = []
        for reg_id, data in stats.items():
            absent = data["Absent"]
            present = total_classes - absent
            percent = (present / total_classes) * 100 if total_classes else 0
            results.append((data["Name"], reg_id, present, absent, percent))

        # Sort by performance
        results.sort(key=lambda x: (-x[4], -x[2]))

        # Group by unique percent levels (top 3 only)
        grouped = {}
        for name, reg, present, absent, percent in results:
            if percent not in grouped:
                grouped[percent] = []
            grouped[percent].append((name, reg, present, absent, percent))

        msg = f"🏆 Top Performers (out of {total_classes} classes):\n\n"
        medals = ["🥇 Top 1", "🥈 Top 2", "🥉 Top 3"]

        for i, (percent, students) in enumerate(grouped.items()):
            if i >= 3:
                break
            sample = students[0]  # for the common stat line
            msg += f"{medals[i]}:\n✅ {sample[2]}, ❌ {sample[3]}, 📊 {sample[4]:.1f}%\n"
            for name, reg, *_ in students:
                msg += f"- {name} ({reg})\n"
            msg += "\n"

        safe_reply(message, msg.strip())

    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)

# ---------------- /refresh (manual reset by teacher) ----------------
@bot.message_handler(commands=['refresh'])
def manual_refresh(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized. Only the teacher can refresh attendance.")
        return
    try:
        attendance_sheet.clear()
        attendance_sheet.append_row(["Name", "Reg ID", "Date", "EasterEgg", "Timestamp", "Telegram ID"])
        with _queue_lock:
            write_queue.clear()
            marked_today_ids.clear()
        invalidate_cache("attendance_rows")
        safe_reply(message, "🔄 Attendance sheet has been manually refreshed successfully.")
        print("🧹 Manual refresh triggered by teacher.")
    except Exception as e:
        safe_reply(message, f"⚠️ Error during manual refresh: {e}")
        print("Manual refresh error:", e)

# ---------------- Flask server (Render) ----------------
app = Flask(__name__)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = f"https://{RENDER_URL}/{BOT_TOKEN}" if RENDER_URL else ""

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
    """Pings both the Render app URL and Telegram API every few minutes."""
    if not RENDER_URL:
        print("⚠️ RENDER_EXTERNAL_URL not set; skipping keep-alive.")
        return
    while True:
        try:
            # 1️⃣ Ping your Render web service so Render doesn't sleep
            requests.get(f"https://{RENDER_URL}/", timeout=10)
            # 2️⃣ Ping Telegram API with getMe() to keep bot session warm
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
            print("🔁 Keep-alive ping sent.")
        except Exception as e:
            print("⚠️ Keep-alive ping failed:", e)
        time.sleep(300)  # every 5 minutes

# ---------------- Webhook setup ----------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not WEBHOOK_URL:
    print("⚠ WEBHOOK_URL not set — skipping webhook setup.")
else:
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Failed to set webhook: {e}")


# ---------------- Start Everything ----------------
if __name__ == "__main__":
    print("🤖 Bot starting on Render...")

    # ---- Set webhook for Telegram ----
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("⚠ WEBHOOK_URL not configured. Please set it in Render environment variables.")
    else:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            print(f"✅ Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            print(f"❌ Failed to set webhook: {e}")

    # ---- Start keep-alive thread (prevents Render sleep) ----
    print("🚀 Keep-alive thread started successfully!")
    print(f"🌍 Pinging: https://{RENDER_URL}/ every 5 min to keep alive...")
    threading.Thread(target=keep_alive, daemon=True).start()
    

    # ---- Initial housekeeping ----
    reset_attendance_if_new_day()
    load_marked_ids_from_sheet()

    # ---- Run Flask app for webhook and health endpoint ----
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
