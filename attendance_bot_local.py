# attendance_bot_local.py — Local test version (identical to Render bot but no MasterList check)

import os
import time
import json
import math
import gspread
import telebot
import threading
from collections import deque
from datetime import datetime
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from flask import Flask, request

# ---------------- Load env ----------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
TIMEZONE = os.getenv("TIMEZONE", "UTC")
CLASS_LAT = float(os.getenv("CLASS_LAT", 0))
CLASS_LON = float(os.getenv("CLASS_LON", 0))
RADIUS_METERS = float(os.getenv("RADIUS_METERS", 100))
STRESS_MODE = os.getenv("STRESS_MODE", "False").lower() == "true"

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set in environment.")
if not SHEET_ID or not SERVICE_ACCOUNT_JSON:
    raise SystemExit("SHEET_ID / SERVICE_ACCOUNT_JSON must be set.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
if TEST_MODE:
    # Monkey-patch send_message so TeleBot doesn't talk to Telegram during stress test
    import types
    def fake_send_message(*a, **k):
        print("⚙ Simulated send_message:", k.get("text", ""))
        return None
    bot.send_message = types.MethodType(fake_send_message, bot)
    bot.reply_to = types.MethodType(fake_send_message, bot)

# ---------------- Google Sheets Auth ----------------
try:
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    print("✅ Google credentials loaded.")
except Exception as e:
    print("❌ Error loading Google credentials:", e)
    raise

attendance_sheet = client.open_by_key(SHEET_ID).worksheet("Attendance")
settings_sheet = client.open_by_key(SHEET_ID).worksheet("Settings")

# ---------------- Helper Functions ----------------
def get_today_date():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

# Cache settings to avoid hitting Google read quota
_cached_settings = None
_last_fetch = 0
def get_settings():
    global _cached_settings, _last_fetch
    now = time.time()
    # refresh only every 5 minutes
    if not _cached_settings or now - _last_fetch > 300:
        try:
            s = settings_sheet.get_all_records()[0]
            _cached_settings = (
                s.get("DailyEasterEgg", "").strip(),
                s.get("StartTime", "00:00").strip(),
                s.get("EndTime", "23:59").strip(),
            )
            _last_fetch = now
        except Exception as e:
            print("⚠ Error refreshing settings:", e)
    return _cached_settings or ("", "00:00", "23:59")

def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# ---------------- Queue System ----------------
write_queue = deque()
_queue_lock = threading.Lock()
BATCH_SIZE = 60
BATCH_FLUSH_INTERVAL = 5
marked_today_ids = set()

# Keep a global counter of how many students were written
written_count = 0
TOTAL_EXPECTED = 1000   # adjust if you test fewer/more

def flush_queue_worker():
    global written_count
    while True:
        try:
            with _queue_lock:
                to_write = []
                while write_queue and len(to_write) < BATCH_SIZE:
                    to_write.append(write_queue.popleft())

            if to_write:
                attendance_sheet.append_rows(to_write, value_input_option='USER_ENTERED')
                written_count += len(to_write)
                print(f"✅ Flushed {len(to_write)} rows. Total written: {written_count}/{TOTAL_EXPECTED}")

                # optional: show progress every 50 students
                if written_count % 50 == 0:
                    print(f"🟢 Progress: {written_count}/{TOTAL_EXPECTED} students written.")

                # when all 1000 done, show confirmation
                if written_count >= TOTAL_EXPECTED:
                    print("\n✅ All 1000 students written successfully to Google Sheet!\n")

            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print(f"⚠ Error writing student {written_count+1}: {e}")
            time.sleep(3)

threading.Thread(target=flush_queue_worker, daemon=True).start()

# ---------------- Telegram Handlers ----------------
user_pending = {}  # telegram_id -> reg_id

def safe_reply(msg, text):
    """Skip replies in stress mode to avoid 400 errors"""
    if not STRESS_MODE:
        try:
            bot.reply_to(msg, text)
        except Exception as e:
            print("⚠ Reply skipped:", e)
    else:
        print(f"💬 [StressMode] {text}")

@bot.message_handler(commands=['start'])
def send_welcome(msg):
    safe_reply(msg, "👋 Send <EasterEgg> <RegID> and then send your 📍 location to mark attendance.")

@bot.message_handler(func=lambda m: m.text is not None and not m.text.startswith('/'))
def handle_easteregg(msg):
    try:
        text = msg.text.strip()
        parts = text.split()
        if len(parts) != 2:
            safe_reply(msg, "❌ Invalid format. Use <EasterEgg> <RegID>")
            return

        easter, reg_id = parts
        daily_egg, start_time, end_time = get_settings()
        if easter.lower() != daily_egg.lower():
            safe_reply(msg, "❌ Wrong Easter Egg.")
            return

        user_pending[msg.from_user.id] = reg_id
        safe_reply(msg, "✅ Verified — now share your 📍 location.")
    except Exception as e:
        safe_reply(msg, f"⚠ Error: {e}")

@bot.message_handler(content_types=['location'])
def handle_location(msg):
    try:
        uid = msg.from_user.id
        if uid not in user_pending:
            safe_reply(msg, "❌ Send <EasterEgg> <RegID> first.")
            return

        reg_id = user_pending.pop(uid)
        user_lat = msg.location.latitude
        user_lon = msg.location.longitude
        dist = distance_m(user_lat, user_lon, CLASS_LAT, CLASS_LON)
        if dist > RADIUS_METERS:
            safe_reply(msg, f"📍 Too far from class ({dist:.1f}m > {RADIUS_METERS}m).")
            return

        today = get_today_date()
        if str(uid) in marked_today_ids:
            safe_reply(msg, "⚠ You’ve already marked attendance today.")
            return

        timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        daily_egg = get_settings()[0]
        student_name = f"Student_{int(reg_id[-4:]):04d}"

        row = [student_name, reg_id, today, daily_egg, timestamp, str(uid)]
        with _queue_lock:
            write_queue.append(row)
            marked_today_ids.add(str(uid))

        safe_reply(msg, f"✅ Attendance queued for {student_name} ({reg_id}) at {timestamp}")
    except Exception as e:
        safe_reply(msg, f"⚠ Error: {e}")

# ---------------- Flask server (Local test mode) ----------------
app = Flask(__name__)
PORT = int(os.getenv("PORT", 10000))

@app.route('/')
def home():
    return "✅ Bot running locally via Flask", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("Webhook error:", e)
        return "Error", 500

if __name__ == "__main__":
    print(f"🚀 Starting bot locally on port {PORT} (Flask test mode, webhook simulation)")
    bot.remove_webhook()
    threading.Thread(
        target=lambda: bot.infinity_polling(timeout=60, long_polling_timeout=60),
        daemon=True
    ).start()
    app.run(host="0.0.0.0", port=PORT)
