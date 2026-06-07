"""
AI Study Partner — Entry Point

Runs as a 24/7 web service on Render (free tier):
  • Flask keep-alive server holds the port open + answers health checks
  • Self-ping every 10 min prevents the free instance from sleeping
  • The Telegram bot itself runs in long-polling mode (no webhook needed)

Works locally too — just run `python main.py` (self-ping auto-disables).

Google credentials:
  Set GOOGLE_CREDENTIALS_JSON to the base64-encoded contents of credentials.json.
  This script decodes it and writes credentials.json at startup.
"""
import base64
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _write_google_credentials() -> None:
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not raw:
        logger.warning("GOOGLE_CREDENTIALS_JSON not set — Google Sheets will fail.")
        return
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(creds_path):
        return
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
    except Exception:
        decoded = raw
    with open(creds_path, "w") as fh:
        fh.write(decoded)
    logger.info("credentials.json written from env var.")


def main() -> None:
    _write_google_credentials()

    from telegram.ext import (
        Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters,
    )

    # ── Core handlers ──────────────────────────────────────────────────────────
    from bot.handlers import (
        done, help_cmd, handle_message, progress, report,
        reschedule, start, stuck, test, today,
    )
    # ── Settings inline UI ─────────────────────────────────────────────────────
    from bot.settings_ui import handle_settings_callback, settings_cmd
    # ── Slides / Gamma ─────────────────────────────────────────────────────────
    from bot.slides_handler import handle_gamma_callback, slides
    # ── Deep research ──────────────────────────────────────────────────────────
    from bot.research_handlers import compare, explain, mnemonic, research
    # ── NotebookLM ─────────────────────────────────────────────────────────────
    from bot.notebooklm_handlers import ask, podcast, upload
    # ── Scheduler ─────────────────────────────────────────────────────────────
    from scheduler.daily_jobs import setup_scheduler
    # ── Keep-alive web server ──────────────────────────────────────────────────
    from keep_alive import start_keep_alive

    token = os.environ["TELEGRAM_BOT_TOKEN"]

    # Clear any leftover webhook before polling (prevents 409 Conflict)
    async def _post_init(application: "Application") -> None:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared — starting long-polling.")

    app = Application.builder().token(token).post_init(_post_init).build()

    # ── Commands ───────────────────────────────────────────────────────────────
    for cmd, fn in [
        ("start",      start),
        ("today",      today),
        ("done",       done),
        ("test",       test),
        ("progress",   progress),
        ("stuck",      stuck),
        ("reschedule", reschedule),
        ("report",     report),
        ("help",       help_cmd),
        ("settings",   settings_cmd),
        ("slides",     slides),
        ("research",   research),
        ("explain",    explain),
        ("compare",    compare),
        ("mnemonic",   mnemonic),
        ("upload",     upload),
        ("ask",        ask),
        ("podcast",    podcast),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # ── Inline callback handlers ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_settings_callback, pattern=r"^settings:"))
    app.add_handler(CallbackQueryHandler(handle_gamma_callback,    pattern=r"^gamma:"))

    # ── Natural language (catch-all text) ──────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # ── Document handler (for /upload PDF) ────────────────────────────────────
    app.add_handler(MessageHandler(filters.Document.PDF, upload))

    # ── Scheduler ─────────────────────────────────────────────────────────────
    setup_scheduler(app)

    # ── Start keep-alive web server (Flask + self-ping) in background ───────────
    start_keep_alive()

    # ── Run the bot (long-polling, main thread) ────────────────────────────────
    logger.info("Bot starting in long-polling mode — running 24/7.")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
