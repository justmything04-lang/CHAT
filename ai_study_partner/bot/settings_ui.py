"""
/settings command + all inline keyboard callbacks.
Users can change briefing time and inactivity mode without touching any config.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from scheduler.daily_jobs import (
    INACTIVITY_LABELS, schedule_user_briefing, schedule_user_inactivity,
)
from state.session import delete_user, get_user, is_onboarded, update_user

logger = logging.getLogger(__name__)


def _main_keyboard(briefing_time: str, inactivity_mode: str) -> InlineKeyboardMarkup:
    label = INACTIVITY_LABELS.get(inactivity_mode, inactivity_mode)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🕐 Briefing: {briefing_time}", callback_data="settings:briefing"),
            InlineKeyboardButton(f"🔔 Alert: {label}", callback_data="settings:alert_menu"),
        ],
        [
            InlineKeyboardButton("📊 View My Sheet", callback_data="settings:sheet"),
            InlineKeyboardButton("🗑️ Reset All Data", callback_data="settings:reset_confirm"),
        ],
    ])


def _alert_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏰ Every Hour",   callback_data="settings:alert:hourly"),
            InlineKeyboardButton("📅 Daily",         callback_data="settings:alert:daily"),
        ],
        [
            InlineKeyboardButton("📆 Every 2 Days", callback_data="settings:alert:2days"),
            InlineKeyboardButton("🗓️ Weekly",        callback_data="settings:alert:weekly"),
        ],
        [
            InlineKeyboardButton("🔕 Never",         callback_data="settings:alert:never"),
            InlineKeyboardButton("← Back",           callback_data="settings:main"),
        ],
    ])


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first to set up your plan.")
        return
    user = get_user(user_id)
    briefing = user.get("briefing_time", "08:00")
    inactivity = user.get("inactivity_mode", "2days")
    await update.message.reply_text(
        f"⚙️ *Settings — {user.get('name', 'Student')}*\n\n"
        f"🕐 Daily Briefing:   `{briefing}`\n"
        f"🔔 Inactivity Alert: `{INACTIVITY_LABELS.get(inactivity, inactivity)}`\n\n"
        "Tap a button to change anything:",
        parse_mode="Markdown",
        reply_markup=_main_keyboard(briefing, inactivity),
    )


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user = get_user(user_id)
    if not user:
        await query.message.reply_text("Session expired. Please /start again.")
        return

    # ── Main settings view ────────────────────────────────────────────────
    if data == "settings:main":
        briefing   = user.get("briefing_time", "08:00")
        inactivity = user.get("inactivity_mode", "2days")
        await query.message.edit_text(
            f"⚙️ *Settings — {user.get('name', 'Student')}*\n\n"
            f"🕐 Daily Briefing:   `{briefing}`\n"
            f"🔔 Inactivity Alert: `{INACTIVITY_LABELS.get(inactivity, inactivity)}`\n\n"
            "Tap a button to change anything:",
            parse_mode="Markdown",
            reply_markup=_main_keyboard(briefing, inactivity),
        )

    # ── Briefing time ─────────────────────────────────────────────────────
    elif data == "settings:briefing":
        update_user(user_id, {"awaiting_setting": "briefing_time"})
        await query.message.reply_text(
            "⏰ Enter your preferred daily briefing time in *HH:MM* format (24-hour):\n\n"
            "Examples: `07:30` `09:00` `18:00`\n\n"
            "_(Times are in the timezone set by the server — default UTC)_",
            parse_mode="Markdown",
        )

    # ── Inactivity menu ───────────────────────────────────────────────────
    elif data == "settings:alert_menu":
        await query.message.edit_text(
            "🔔 *How often should I check in if you go quiet?*\n\n"
            "I'll only message you if you haven't interacted with the bot for this long:",
            parse_mode="Markdown",
            reply_markup=_alert_keyboard(),
        )

    elif data.startswith("settings:alert:"):
        mode = data.split(":")[-1]
        update_user(user_id, {"inactivity_mode": mode})
        schedule_user_inactivity(context.application, user_id, mode)
        label = INACTIVITY_LABELS.get(mode, mode)
        briefing = user.get("briefing_time", "08:00")
        await query.message.edit_text(
            f"✅ Inactivity alert set to *{label}*\n\n"
            f"⚙️ *Settings — {user.get('name', 'Student')}*\n\n"
            f"🕐 Daily Briefing:   `{briefing}`\n"
            f"🔔 Inactivity Alert: `{label}`",
            parse_mode="Markdown",
            reply_markup=_main_keyboard(briefing, mode),
        )

    # ── View sheet ────────────────────────────────────────────────────────
    elif data == "settings:sheet":
        sheet_url = user.get("sheet_url", "Not available yet.")
        await query.message.reply_text(f"📊 Your Google Sheet:\n{sheet_url}")

    # ── Reset confirmation ────────────────────────────────────────────────
    elif data == "settings:reset_confirm":
        await query.message.edit_text(
            "⚠️ *Are you sure?*\n\n"
            "This will delete all your session data (name, goal, sheet link, progress).\n"
            "Your Google Sheet itself will *not* be deleted.\n\n"
            "You will need to /start again from scratch.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, reset", callback_data="settings:reset_do"),
                InlineKeyboardButton("❌ Cancel",      callback_data="settings:main"),
            ]]),
        )

    elif data == "settings:reset_do":
        # Cancel all scheduled jobs for this user
        for job in context.application.job_queue.get_jobs_by_name(f"briefing_{user_id}"):
            job.schedule_removal()
        for job in context.application.job_queue.get_jobs_by_name(f"inactivity_{user_id}"):
            job.schedule_removal()
        delete_user(user_id)
        await query.message.edit_text(
            "🗑️ All data deleted.\n\nUse /start to begin again."
        )
