# attendance_bot_local.py
import os
import time
import json
import math
import gspread
import telebot
import threading
from collections import deque
from flask import Flask, request
from datetime import datetime
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# ---------------- Load env ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "TEST_TOKEN_123")
SHEET_ID = os.getenv("SHEET_ID")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
TIMEZONE = os.getenv("TIMEZONE", "UTC")
CLASS_LAT = float(os.getenv("CLASS_LAT", 12.95))
CLASS_LON = float(os.getenv("CLASS_LON", 80.16))
RADIUS_METERS = float(os.getenv("RADIUS_METERS", 250))
PORT = int(os.getenv("PORT", 10000))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ---------------- Google Sheets ----------------
try:
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    print("✅ Google credentials loaded.")
except Exception as e:
    print("❌ Error loading credentials:", e)
    raise

attendance_sheet = client.open_by_key(SHEET_ID).worksheet("Attendance")
online_attendance_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineAttendance")

# ---------------- Queue ----------------
write_queue = deque()
_queue_lock = threading.Lock()
BATCH_SIZE = 80
BATCH_FLUSH_INTERVAL = 5
marked_today_ids = set()
marked_today_online_ids = set()

def get_today():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

def flush_queue_worker():
    while True:
        try:
            with _queue_lock:
                to_write_offline = []
                to_write_online = []
                while write_queue and (len(to_write_offline)+len(to_write_online)) < BATCH_SIZE:
                    mode, row = write_queue.popleft()
                    if mode == "offline":
                        to_write_offline.append(row)
                    else:
                        to_write_online.append(row)
            if to_write_offline:
                attendance_sheet.append_rows(to_write_offline, value_input_option="USER_ENTERED")
                print(f"✅ Flushed {len(to_write_offline)} offline rows.")
            if to_write_online:
                online_attendance_sheet.append_rows(to_write_online, value_input_option="USER_ENTERED")
                print(f"✅ Flushed {len(to_write_online)} online rows.")
            time.sleep(BATCH_FLUSH_INTERVAL)
        except Exception as e:
            print("⚠️ Flush error:", e)
            time.sleep(3)

threading.Thread(target=flush_queue_worker, daemon=True).start()

# ---------------- Handlers ----------------
@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def handle_easteregg(msg):
    try:
        text = msg.text.strip()
        parts = text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Invalid format. Use <Egg> <RegID>")
            return

        easter, reg_id = parts
        today = get_today()
        ts = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

        # 👇 NO master list verification for local test
        student_name = f"Student_{reg_id}"

        # If message contains "[ONLINE]" → mark online
        if "[ONLINE]" in text.upper():
            row = [student_name, reg_id, today, easter, ts, str(msg.from_user.id)]
            with _queue_lock:
                write_queue.append(("online", row))
            bot.reply_to(msg, f"✅ Online attendance queued for {student_name} ({reg_id})")
        else:
            # Offline requires fake location too
            row = [student_name, reg_id, today, easter, ts, str(msg.from_user.id)]
            with _queue_lock:
                write_queue.append(("offline", row))
            bot.reply_to(msg, f"✅ Offline attendance queued for {student_name} ({reg_id})")
    except Exception as e:
        bot.reply_to(msg, f"⚠️ Error: {e}")

# ---------------- Flask webhook ----------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "✅ Local Bot running (webhook mode)", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("Webhook error:", e)
        return "Error", 500

if __name__ == "__main__":
    print(f"🚀 Local bot running at http://127.0.0.1:{PORT}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=PORT)
