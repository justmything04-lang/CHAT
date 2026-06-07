"""
AI Study Partner — Entry Point
  Local dev  : runs in polling mode  (no RENDER_APP_URL set)
  Production : runs in webhook mode  (RENDER_APP_URL set in Render env vars)

Google credentials:
  Set GOOGLE_CREDENTIALS_JSON to the base64-encoded contents of credentials.json
  This script decodes it and writes credentials.json at startup.
"""
import os
import base64
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _write_google_credentials() -> None:
    """Decode GOOGLE_CREDENTIALS_JSON (base64) and write to credentials.json."""
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not raw:
        logger.warning("GOOGLE_CREDENTIALS_JSON is not set — Google Sheets will fail.")
        return

    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(creds_path):
        return  # already present (local dev with real file)

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
    except Exception:
        decoded = raw  # already plain JSON

    with open(creds_path, "w") as fh:
        fh.write(decoded)
    logger.info("credentials.json written from GOOGLE_CREDENTIALS_JSON env var.")


def main() -> None:
    _write_google_credentials()

    # Import after credentials are in place
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    from bot.handlers import (
        start, today, done, test, progress, stuck,
        reschedule, report, help_cmd, handle_message,
    )
    from scheduler.daily_jobs import setup_scheduler

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # ── Command handlers ────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("today",      today))
    app.add_handler(CommandHandler("done",       done))
    app.add_handler(CommandHandler("test",       test))
    app.add_handler(CommandHandler("progress",   progress))
    app.add_handler(CommandHandler("stuck",      stuck))
    app.add_handler(CommandHandler("reschedule", reschedule))
    app.add_handler(CommandHandler("report",     report))
    app.add_handler(CommandHandler("help",       help_cmd))

    # ── Natural language handler ─────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ── Scheduled jobs ───────────────────────────────────────────────────────
    setup_scheduler(app)

    # ── Run ──────────────────────────────────────────────────────────────────
    render_url = os.getenv("RENDER_APP_URL", "").rstrip("/")
    port = int(os.getenv("PORT", 10000))

    if render_url:
        logger.info("Webhook mode — listening on port %s", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{render_url}/{token}",
        )
    else:
        logger.info("Polling mode (local development)")
        app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
