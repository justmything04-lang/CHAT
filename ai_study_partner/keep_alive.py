"""
Keep-alive web server — makes the bot run 24/7 on Render's free tier.

Render spins a free web service DOWN after ~15 min with no inbound HTTP traffic.
This module prevents that:
  1. Runs a tiny Flask server so Render sees an open port + a healthy service.
  2. Self-pings RENDER_APP_URL every 10 min so the idle timer never trips.

For 100% bulletproof uptime, ALSO point an external monitor
(UptimeRobot or cron-job.org) at your RENDER_APP_URL/health endpoint.
An external monitor can even WAKE the service if it ever does sleep —
a self-ping cannot (a sleeping process can't ping itself).
"""
import logging
import os
import threading
import time

from flask import Flask

logger = logging.getLogger(__name__)

# Quiet Flask's per-request access logs (keep our own logs readable)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "🤖 AI Study Partner is alive and running 24/7!", 200


@flask_app.route("/health")
def health():
    return {"status": "ok", "service": "ai-study-partner"}, 200


def _run_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    # use_reloader=False is required when running outside the main thread
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


def _self_ping() -> None:
    url = os.getenv("RENDER_APP_URL", "").rstrip("/")
    if not url:
        logger.info("RENDER_APP_URL not set — self-ping disabled (local mode).")
        return
    interval = int(os.getenv("KEEP_ALIVE_SECONDS", "600"))  # 10 min default
    import requests
    while True:
        time.sleep(interval)
        try:
            r = requests.get(f"{url}/health", timeout=15)
            logger.info("Keep-alive ping → %s/health (%s)", url, r.status_code)
        except Exception as exc:
            logger.warning("Keep-alive ping failed: %s", exc)


def start_keep_alive() -> None:
    """Start the Flask server + self-ping loop as background daemon threads."""
    threading.Thread(target=_run_server, daemon=True, name="flask-keepalive").start()
    threading.Thread(target=_self_ping, daemon=True, name="self-ping").start()
    logger.info("Keep-alive web server live on port %s", os.getenv("PORT", "10000"))
