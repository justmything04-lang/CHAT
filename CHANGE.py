# stress_test.py — local simulator (offline 2500 + online 8000)

import os
import asyncio
import aiohttp
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
EASTER_EGG = os.getenv("EASTER_EGG", "Zen")
LAT = float(os.getenv("CLASS_LAT", 0))
LON = float(os.getenv("CLASS_LON", 0))

BOT_URL = f"http://127.0.0.1:{PORT}/{BOT_TOKEN}"

COUNT_OFFLINE = 2500
COUNT_ONLINE = 8000
CONCURRENCY = 100
WAIT_BETWEEN = 0.2

async def mark_offline(session, student_id):
    reg_id = f"STU{student_id:04d}"
    payload = {
        "update_id": student_id,
        "message": {"message_id": student_id,"from": {"id": student_id},"chat": {"id": student_id,"type": "private"},"text": f"{EASTER_EGG} {reg_id}"}
    }
    await session.post(BOT_URL, json=payload)
    await asyncio.sleep(WAIT_BETWEEN)
    loc_payload = {
        "update_id": student_id+10000,
        "message": {"message_id": student_id+10000,"from": {"id": student_id},"chat": {"id": student_id,"type": "private"},"location": {"latitude": LAT,"longitude": LON}}
    }
    await session.post(BOT_URL, json=loc_payload)

async def mark_online(session, student_id):
    reg_id = f"ON{student_id:05d}"
    payload = {
        "update_id": 50000+student_id,
        "message": {"message_id": 50000+student_id,"from": {"id": 50000+student_id},"chat": {"id": 50000+student_id,"type": "private"},"text": f"{EASTER_EGG} {reg_id}"}
    }
    await session.post(BOT_URL, json=payload)

async def stress_test():
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i in range(1, COUNT_OFFLINE+1):
            tasks.append(mark_offline(session, i))
        for j in range(1, COUNT_ONLINE+1):
            tasks.append(mark_online(session, j))
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    print(f"🚀 Stress test starting: {COUNT_OFFLINE} offline + {COUNT_ONLINE} online")
    start = datetime.now()
    asyncio.run(stress_test())
    end = datetime.now()
    print(f"✅ Stress test complete in {(end-start).total_seconds():.2f}s")
