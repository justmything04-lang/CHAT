# stress_test_local.py
import os
import json
import time
import random
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "TEST_TOKEN_123")
PORT = int(os.getenv("PORT", 10000))
URL = f"http://127.0.0.1:{PORT}/{BOT_TOKEN}"

def send_update(user_id, text, mode="offline"):
    update = {
        "update_id": random.randint(100000, 999999),
        "message": {
            "message_id": random.randint(1, 9999),
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "TestUser"
            },
            "chat": {
                "id": user_id,
                "type": "private"
            },
            "date": int(time.time()),
            "text": text if mode == "offline" else f"{text} [ONLINE]"
        }
    }
    try:
        r = requests.post(URL, data=json.dumps(update), headers={"Content-Type": "application/json"})
        if r.status_code != 200:
            print("⚠️ Failed update:", r.text)
    except Exception as e:
        print("Error sending:", e)

print("🚀 Stress test started...")

# Offline = 2500 students
for i in range(1, 2501):
    reg = f"STU{i:04d}"
    send_update(10000+i, f"Egg {reg}", mode="offline")
    if i % 500 == 0:
        print(f"✅ Sent {i}/2500 offline students")
    time.sleep(0.01)

# Online = 8000 students
for i in range(1, 8001):
    reg = f"ON{i:04d}"
    send_update(20000+i, f"Egg {reg}", mode="online")
    if i % 1000 == 0:
        print(f"✅ Sent {i}/8000 online students")
    time.sleep(0.005)

print("🎉 Stress test finished. Check your Sheets now!")
