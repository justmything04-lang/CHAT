"""
Scheduled jobs:
  • 08:00 daily  — morning briefing for every onboarded user
  • 09:00 daily  — inactivity follow-up (2+ days silent)
"""
import logging
import datetime as dt

from telegram.ext import Application

from state.session import get_all_users
from sheets.sheets_manager import (
    get_todays_topics, get_progress_summary, get_weak_areas,
)
from ai.gemini_client import generate_daily_briefing

logger = logging.getLogger(__name__)


async def _send_daily_briefing(context) -> None:
    for uid, data in get_all_users().items():
        if data.get("onboarding_step") != "complete":
            continue
        try:
            topics = get_todays_topics(data["sheet_id"])
            summary = get_progress_summary(data["sheet_id"])
            weak = get_weak_areas(data["sheet_id"])

            topic_str = ", ".join(t.get("Topic", "") for t in topics[:3]) or "No new topics"
            weak_str = ", ".join(w.get("Topic", "") for w in weak[:3]) or "None"

            end_dt = dt.datetime.strptime(
                data.get("end_date", dt.datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
            )
            days_left = max(0, (end_dt - dt.datetime.now()).days)

            briefing = generate_daily_briefing(
                data.get("name", "Student"),
                data.get("goal", "your goal"),
                topic_str,
                days_left,
                summary.get("percentage", 0),
                weak_str,
            )

            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    f"🌅 *Good morning, {data.get('name', 'Student')}!*\n\n"
                    f"{briefing}\n\n"
                    "Use /today to see full targets."
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Daily briefing failed for %s: %s", uid, exc)


async def _check_inactivity(context) -> None:
    now = dt.datetime.now()
    for uid, data in get_all_users().items():
        if data.get("onboarding_step") != "complete":
            continue
        last_str = data.get("last_active", "")
        if not last_str:
            continue
        try:
            last = dt.datetime.fromisoformat(last_str)
            days_away = (now - last).days
            if days_away >= 2:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"👋 Hey {data.get('name', 'there')}!\n\n"
                        f"You've been away for *{days_away} day(s)*. "
                        "Your study streak is at risk! 😟\n\n"
                        "Use /reschedule to adjust your plan and /today to get back on track.\n"
                        "You can do this! 💪"
                    ),
                    parse_mode="Markdown",
                )
        except Exception as exc:
            logger.error("Inactivity check failed for %s: %s", uid, exc)


def setup_scheduler(application: Application) -> None:
    jq = application.job_queue
    jq.run_daily(_send_daily_briefing, time=dt.time(hour=8, minute=0), name="daily_briefing")
    jq.run_daily(_check_inactivity,   time=dt.time(hour=9, minute=0), name="inactivity_check")
    logger.info("Scheduler ready: briefing @08:00, inactivity check @09:00")
