# stress_test_local.py — for local webhook stress test

import os
import time
import random
import requests
from dotenv import load_dotenv

# Load from .env (so it's the SAME token your bot uses)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")  # must match your attendance_bot_local.py
PORT = int(os.getenv("PORT", 10000))  # same as your Flask port

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN missing in .env (must be set).")

URL = f"http://127.0.0.1:{PORT}/{BOT_TOKEN}"

print(f"🚀 Stress test starting for local bot at {URL}")

TOTAL_OFFLINE = 2500
TOTAL_ONLINE = 8000

def simulate_student(reg_id, mode="offline"):
    """Send fake update to Flask webhook"""
    if mode == "offline":
        fake_update = {
            "update_id": random.randint(100000, 999999),
            "message": {
                "message_id": random.randint(1000, 9999),
                "from": {"id": reg_id, "is_bot": False, "first_name": f"Offline{reg_id}"},
                "chat": {"id": reg_id, "type": "private"},
                "date": int(time.time()),
                "text": f"egg STU{reg_id:04d}"
            }
        }
    else:  # online mode
        fake_update = {
            "update_id": random.randint(100000, 999999),
            "message": {
                "message_id": random.randint(1000, 9999),
                "from": {"id": reg_id, "is_bot": False, "first_name": f"Online{reg_id}"},
                "chat": {"id": reg_id, "type": "private"},
                "date": int(time.time()),
                "text": f"egg STU{reg_id:04d}"
            }
        }

    try:
        r = requests.post(URL, json=fake_update, timeout=5)
        if r.status_code != 200:
            print(f"⚠️ Failed update for {mode} {reg_id}: {r.text[:100]}")
    except Exception as e:
        print(f"⚠️ Request error for {mode} {reg_id}: {e}")

# ---------------- Run Stress ----------------
start = time.time()

# Offline batch
print(f"➡ Sending {TOTAL_OFFLINE} offline students...")
for i in range(1, TOTAL_OFFLINE + 1):
    simulate_student(i, mode="offline")
print("✅ Offline simulation complete.")

# Online batch
print(f"➡ Sending {TOTAL_ONLINE} online students...")
for i in range(1, TOTAL_ONLINE + 1):
    simulate_student(i, mode="online")
print("✅ Online simulation complete.")

elapsed = time.time() - start
print(f"\n🎉 Stress test complete in {elapsed:.1f} seconds.")
