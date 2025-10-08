# attendance_bot_local.py — Local test (Flask webhook mode, offline + online, no MasterList check)

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
STRESS_MODE = os.getenv("STRESS_MODE", "false").lower() == "true"

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set in environment.")
if not SHEET_ID or not SERVICE_ACCOUNT_JSON:
    raise SystemExit("SHEET_ID / SERVICE_ACCOUNT_JSON must be set.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# Monkey patch for stress mode
if STRESS_MODE:
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
online_attendance_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineAttendance")
settings_sheet = client.open_by_key(SHEET_ID).worksheet("Settings")

# ---------------- Helpers ----------------
def get_today_date():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# ---------------- Queue System ----------------
write_queue = deque()
_queue_lock = threading.Lock()
BATCH_SIZE = 60
BATCH_FLUSH_INTERVAL = 5

written_count = 0
TOTAL_EXPECTED = 10500  # 2500 offline + 8000 online

def flush_queue_worker():
    global written_count
    while True:
        try:
            with _queue_lock:
                to_write_offline = []
                to_write_online = []
                while write_queue and (len(to_write_offline) + len(to_write_online)) < BATCH_SIZE:
                    mode, row = write_queue.popleft()
                    if mode == "offline":
                        to_write_offline.append(row)
                    else:
                        to_write_online.append(row)

            if to_write_offline:
                attendance_sheet.append_rows(to_write_offline, value_input_option='USER_ENTERED')
                written_count += len(to_write_offline)
                print(f"✅ Flushed {len(to_write_offline)} offline rows. Total written: {written_count}/{TOTAL_EXPECTED}")

            if to_write_online:
                online_attendance_sheet.append_rows(to_write_online, value_input_option='USER_ENTERED')
                written_count += len(to_write_online)
                print(f"✅ Flushed {len(to_write_online)} online rows. Total written: {written_count}/{TOTAL_EXPECTED}")

            if written_count % 500 == 0:
                print(f"🟢 Progress: {written_count}/{TOTAL_EXPECTED} students written.")

            if written_count >= TOTAL_EXPECTED:
                print("\n✅ All students written successfully to Google Sheet!\n")

            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print("⚠ Batch worker error:", e)
            time.sleep(3)

threading.Thread(target=flush_queue_worker, daemon=True).start()

# ---------------- Telegram Handlers ----------------
user_pending = {}

def safe_reply(msg, text):
    if not STRESS_MODE:
        try:
            bot.reply_to(msg, text)
        except Exception as e:
            print("⚠ Reply skipped:", e)
    else:
        print(f"💬 [StressMode] {text}")

@bot.message_handler(commands=['start'])
def send_welcome(msg):
    safe_reply(msg, "👋 Choose mode:\n🧑‍🏫 Offline (location required)\n💻 Online (EasterEgg only)")

@bot.message_handler(func=lambda m: m.text == "🧑‍🏫 Offline")
def offline_mode(msg):
    user_pending[msg.from_user.id] = {"mode": "offline"}
    safe_reply(msg, "📍 Offline mode selected. Send `<EasterEgg> <RegID>` then location.")

@bot.message_handler(func=lambda m: m.text == "💻 Online")
def online_mode(msg):
    user_pending[msg.from_user.id] = {"mode": "online"}
    safe_reply(msg, "💻 Online mode selected. Send `<EasterEgg> <RegID>` only.")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def handle_easteregg(msg):
    parts = msg.text.strip().split()
    if len(parts) != 2:
        safe_reply(msg, "❌ Invalid format. Use `<EasterEgg> <RegID>`")
        return
    easter, reg_id = parts
    pending = user_pending.get(msg.from_user.id, {})
    mode = pending.get("mode", "offline")

    today = get_today_date()
    timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    student_name = f"Student_{int(reg_id[-4:]):04d}" if reg_id[-4:].isdigit() else f"Student_{reg_id}"

    if mode == "online":
        row = [student_name, reg_id, today, easter, timestamp, str(msg.from_user.id)]
        with _queue_lock:
            write_queue.append(("online", row))
        safe_reply(msg, f"✅ Online attendance queued for {student_name} ({reg_id}) at {timestamp}")
    else:
        user_pending[msg.from_user.id] = {"mode": "offline", "reg_id": reg_id}
        safe_reply(msg, "✅ Verified — now share 📍 location.")

@bot.message_handler(content_types=['location'])
def handle_location(msg):
    pending = user_pending.get(msg.from_user.id)
    if not pending or pending.get("mode") != "offline":
        safe_reply(msg, "❌ Send `<EasterEgg> <RegID>` first in Offline mode.")
        return
    reg_id = pending.get("reg_id")
    today = get_today_date()
    timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    student_name = f"Student_{int(reg_id[-4:]):04d}" if reg_id[-4:].isdigit() else f"Student_{reg_id}"
    row = [student_name, reg_id, today, "EGG", timestamp, str(msg.from_user.id)]
    with _queue_lock:
        write_queue.append(("offline", row))
    safe_reply(msg, f"✅ Offline attendance queued for {student_name} ({reg_id}) at {timestamp}")
    user_pending.pop(msg.from_user.id, None)

# ---------------- Flask (Webhook) ----------------
app = Flask(__name__)
PORT = int(os.getenv("PORT", 10000))

@app.route('/')
def home():
    return "✅ Local Attendance Bot (Flask webhook mode)", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("Webhook error:", e)
        return "Error", 500

if __name__ == "__main__":
    print(f"🚀 Starting bot locally on port {PORT}")
    bot.remove_webhook()
    app.run(host="0.0.0.0", port=PORT)
