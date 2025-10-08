# stress_test_local.py — fixed with full flow (offline + online)

import os
import time
import random
import requests
from dotenv import load_dotenv

# Load from .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
URL = f"http://127.0.0.1:{PORT}/{BOT_TOKEN}"

TOTAL_OFFLINE = 2500
TOTAL_ONLINE = 8000

def simulate_offline_student(reg_id):
    """Send both egg text and location for offline student"""
    chat_id = reg_id + 100000  # avoid overlap
    # Step 1: EasterEgg + RegID
    egg_update = {
        "update_id": random.randint(100000, 999999),
        "message": {
            "message_id": random.randint(1000, 9999),
            "from": {"id": chat_id, "is_bot": False, "first_name": f"Offline{reg_id}"},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time.time()),
            "text": f"egg STU{reg_id:04d}"
        }
    }
    requests.post(URL, json=egg_update, timeout=5)

    # Step 2: Location
    loc_update = {
        "update_id": random.randint(100000, 999999),
        "message": {
            "message_id": random.randint(1000, 9999),
            "from": {"id": chat_id, "is_bot": False, "first_name": f"Offline{reg_id}"},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time.time()),
            "location": {"latitude": 12.9551, "longitude": 80.1696}  # within radius
        }
    }
    requests.post(URL, json=loc_update, timeout=5)

def simulate_online_student(reg_id):
    """Send only egg text for online student"""
    chat_id = reg_id + 200000  # separate id space
    egg_update = {
        "update_id": random.randint(100000, 999999),
        "message": {
            "message_id": random.randint(1000, 9999),
            "from": {"id": chat_id, "is_bot": False, "first_name": f"Online{reg_id}"},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time.time()),
            "text": f"egg STU{reg_id:04d}"
        }
    }
    requests.post(URL, json=egg_update, timeout=5)

# ---------------- Run Stress ----------------
start = time.time()

print(f"➡ Sending {TOTAL_OFFLINE} offline students...")
for i in range(1, TOTAL_OFFLINE + 1):
    simulate_offline_student(i)
    if i % 500 == 0:
        print(f"🟢 Offline progress: {i}/{TOTAL_OFFLINE}")
print("✅ Offline simulation complete.")

print(f"➡ Sending {TOTAL_ONLINE} online students...")
for i in range(1, TOTAL_ONLINE + 1):
    simulate_online_student(i)
    if i % 1000 == 0:
        print(f"🟢 Online progress: {i}/{TOTAL_ONLINE}")
print("✅ Online simulation complete.")

elapsed = time.time() - start
print(f"\n🎉 Stress test complete in {elapsed:.1f} seconds.")
