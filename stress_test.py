# stress_test.py — local load simulator for attendance_bot_local.py (Flask webhook mode)

import os
import asyncio
import aiohttp
import json
import random
from datetime import datetime
from dotenv import load_dotenv

# ---------------- Load environment variables ----------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
EASTER_EGG = os.getenv("EASTER_EGG", "Zen")
LAT = float(os.getenv("CLASS_LAT", 0))
LON = float(os.getenv("CLASS_LON", 0))

BOT_URL = f"http://127.0.0.1:{PORT}/{BOT_TOKEN}"  # must match Flask route

# ---------------- Tuning parameters ----------------
COUNT = 1000        # total simulated students
CONCURRENCY = 50    # concurrent requests
WAIT_BETWEEN = 0.5  # seconds between text & location messages per student

# ---------------- Simulate one student's attendance ----------------
async def mark_one(session, student_id):
    reg_id = f"STU{student_id:04d}"
    name = f"Student_{student_id:04d}"

    # Step 1: Send "<EasterEgg> <RegID>"
    payload = {
        "update_id": student_id,
        "message": {
            "message_id": student_id,
            "from": {"id": student_id, "is_bot": False, "first_name": name},
            "chat": {"id": student_id, "type": "private"},
            "date": int(datetime.now().timestamp()),
            "text": f"{EASTER_EGG} {reg_id}"
        }
    }

    async with session.post(BOT_URL, json=payload) as resp:
        await resp.text()

    # Small wait to simulate user delay
    await asyncio.sleep(WAIT_BETWEEN)

    # Step 2: Send location
    loc_payload = {
        "update_id": student_id + 10000,
        "message": {
            "message_id": student_id + 10000,
            "from": {"id": student_id, "is_bot": False, "first_name": name},
            "chat": {"id": student_id, "type": "private"},
            "date": int(datetime.now().timestamp()),
            "location": {"latitude": LAT, "longitude": LON}
        }
    }

    async with session.post(BOT_URL, json=loc_payload) as resp:
        await resp.text()

# ---------------- Stress test runner ----------------
async def stress_test():
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [mark_one(session, i) for i in range(1, COUNT + 1)]
        await asyncio.gather(*tasks)

# ---------------- Main ----------------
if __name__ == "__main__":
    print(f"🚀 Stress test starting for {COUNT} simulated students...")
    print(f"➡ Sending updates to {BOT_URL}")
    start = datetime.now()
    asyncio.run(stress_test())
    end = datetime.now()
    print(f"✅ Stress test complete in {(end - start).total_seconds():.2f}s.")
