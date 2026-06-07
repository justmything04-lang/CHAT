"""
Per-user dynamic job scheduling.
Every user gets their own briefing and inactivity jobs, configurable from Telegram.
"""
import datetime as dt
import logging
import os

import pytz
from telegram.ext import Application

from ai.gemini_client import generate_daily_briefing
from sheets.sheets_manager import get_progress_summary, get_todays_topics, get_weak_areas
from state.session import get_all_users, get_user

logger = logging.getLogger(__name__)

INACTIVITY_INTERVALS: dict[str, int | None] = {
    "hourly": 3600,
    "daily":  86400,
    "2days":  2 * 86400,
    "weekly": 7 * 86400,
    "never":  None,
}

INACTIVITY_LABELS: dict[str, str] = {
    "hourly": "Every Hour",
    "daily":  "Every Day",
    "2days":  "Every 2 Days",
    "weekly": "Every Week",
    "never":  "Never",
}


def _tz() -> dt.tzinfo:
    return pytz.timezone(os.getenv("TIMEZONE", "UTC"))


def _parse_time(time_str: str) -> dt.time:
    """Parse 'HH:MM' into a tz-aware time object."""
    h, m = map(int, time_str.split(":"))
    return dt.time(hour=h, minute=m, tzinfo=_tz())


# ─── Briefing ────────────────────────────────────────────────────────────────

async def _briefing_callback(context) -> None:
    job = context.job
    user_id: int = job.data["user_id"]
    user = get_user(user_id)
    if not user or user.get("onboarding_step") != "complete":
        return
    try:
        topics    = get_todays_topics(user["sheet_id"])
        summary   = get_progress_summary(user["sheet_id"])
        weak      = get_weak_areas(user["sheet_id"])
        topic_str = ", ".join(t.get("Topic", "") for t in topics[:3]) or "No new topics today"
        weak_str  = ", ".join(w.get("Topic", "") for w in weak[:3]) or "None"
        end_dt    = dt.datetime.strptime(
            user.get("end_date", dt.datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
        )
        days_left = max(0, (end_dt - dt.datetime.now()).days)
        briefing  = generate_daily_briefing(
            user.get("name", "Student"),
            user.get("goal", "your goal"),
            topic_str, days_left,
            summary.get("percentage", 0),
            weak_str,
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🌅 *Good morning, {user.get('name', 'Student')}!*\n\n"
                f"{briefing}\n\n"
                "Use /today to see full targets."
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("Briefing failed for %s: %s", user_id, exc)


def schedule_user_briefing(app: Application, user_id: int, time_str: str) -> None:
    """Cancel existing briefing job and schedule a new one at time_str (HH:MM)."""
    jq = app.job_queue
    for job in jq.get_jobs_by_name(f"briefing_{user_id}"):
        job.schedule_removal()
    jq.run_daily(
        _briefing_callback,
        time=_parse_time(time_str),
        name=f"briefing_{user_id}",
        chat_id=user_id,
        data={"user_id": user_id},
    )
    logger.info("Briefing scheduled for user %s at %s", user_id, time_str)


# ─── Inactivity ───────────────────────────────────────────────────────────────

async def _inactivity_callback(context) -> None:
    job = context.job
    user_id: int = job.data["user_id"]
    mode: str = job.data["mode"]
    user = get_user(user_id)
    if not user or user.get("onboarding_step") != "complete":
        return
    last_str = user.get("last_active", "")
    if not last_str:
        return
    try:
        last = dt.datetime.fromisoformat(last_str)
        threshold = INACTIVITY_INTERVALS.get(mode) or 0
        gap = (dt.datetime.now() - last).total_seconds()
        if gap < threshold:
            return  # user was active recently, skip
        days_away = int(gap // 86400) or 1
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"👋 Hey {user.get('name', 'there')}!\n\n"
                f"You've been away for *{days_away} day(s)*. Your study streak is at risk! 😟\n\n"
                "• /reschedule — adjust your plan\n"
                "• /today — see what's pending\n\n"
                "You can still do this! 💪"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("Inactivity check failed for %s: %s", user_id, exc)


def schedule_user_inactivity(app: Application, user_id: int, mode: str) -> None:
    """Cancel existing inactivity job and schedule a new one per mode."""
    jq = app.job_queue
    for job in jq.get_jobs_by_name(f"inactivity_{user_id}"):
        job.schedule_removal()
    interval = INACTIVITY_INTERVALS.get(mode)
    if interval is None:
        logger.info("Inactivity alerts disabled for user %s", user_id)
        return
    jq.run_repeating(
        _inactivity_callback,
        interval=interval,
        first=interval,
        name=f"inactivity_{user_id}",
        chat_id=user_id,
        data={"user_id": user_id, "mode": mode},
    )
    logger.info("Inactivity job scheduled for user %s: %s", user_id, mode)


# ─── Startup loader ───────────────────────────────────────────────────────────

def setup_scheduler(app: Application) -> None:
    """Restore per-user jobs for all already-onboarded users at startup."""
    users = get_all_users()
    count = 0
    for uid_str, data in users.items():
        if data.get("onboarding_step") != "complete":
            continue
        uid = int(uid_str)
        schedule_user_briefing(app, uid, data.get("briefing_time", "08:00"))
        schedule_user_inactivity(app, uid, data.get("inactivity_mode", "2days"))
        count += 1
    logger.info("Scheduler initialised — %s user job(s) loaded", count)
