"""
Core Telegram command and message handlers.
Onboarding: awaiting_name → awaiting_goal → awaiting_end_date → complete
"""
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ai.gemini_client import (
    create_study_plan, evaluate_progress, generate_mcq_test,
    generate_progress_report, reschedule_plan,
)
from bot.nlp_router import route_message
from scheduler.daily_jobs import schedule_user_briefing, schedule_user_inactivity
from sheets.sheets_manager import (
    add_test_result, create_study_sheet, get_pending_topics,
    get_progress_summary, get_todays_topics, get_weak_areas,
    log_progress, mark_topic_done, update_dashboard,
    update_weak_area, write_study_plan,
)
from state.session import (
    get_quiz_state, get_user, is_onboarded,
    set_quiz_state, update_user,
)

logger = logging.getLogger(__name__)


# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user and user.get("onboarding_step") == "complete":
        await update.message.reply_text(
            f"Welcome back, *{user['name']}*! 👋\n\nUse /today or /help.",
            parse_mode="Markdown",
        )
        return
    update_user(user_id, {"onboarding_step": "awaiting_name"})
    await update.message.reply_text(
        "🤖 *Welcome to AI Study Partner!*\n\n"
        "I'll create your personalised study plan, track progress, quiz you, "
        "generate slides and research — all from this chat!\n\n"
        "Let's start. *What's your name?*",
        parse_mode="Markdown",
    )


# ─── /today ───────────────────────────────────────────────────────────────────

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    user = get_user(user_id)
    await update.message.reply_text("📅 Fetching today's targets…")
    try:
        topics = get_todays_topics(user["sheet_id"])
    except Exception as exc:
        logger.error("get_todays_topics: %s", exc)
        await update.message.reply_text("❌ Could not read your sheet. Try again.")
        return
    if not topics:
        await update.message.reply_text(
            "✅ Nothing pending for today — you're ahead of schedule!\n"
            "Use /progress to check overall status."
        )
        return
    lines = ["📚 *Today's Study Targets:*\n"]
    total_h = 0.0
    for t in topics:
        lines.append(f"▶ *{t.get('Topic', '?')}*")
        if t.get("Subtopics"):
            lines.append(f"  _{t['Subtopics']}_")
        lines.append(f"  ⏱ {t.get('Est. Hours', 1)}h  |  📊 {t.get('Difficulty', 'MEDIUM')}\n")
        try:
            total_h += float(t.get("Est. Hours", 0))
        except (ValueError, TypeError):
            pass
    lines.append(f"⏰ *Total: {total_h:.1f} hours*")
    lines.append("\nDone? Say _'I finished [topic]'_ or use /done [topic]")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── /done ────────────────────────────────────────────────────────────────────

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: `/done Chapter 3`", parse_mode="Markdown")
        return
    user = get_user(user_id)
    try:
        if not mark_topic_done(user["sheet_id"], topic):
            await update.message.reply_text(
                f"⚠️ Could not find *{topic}* in your plan. Check /today for exact names.",
                parse_mode="Markdown",
            )
            return
        summary = get_progress_summary(user["sheet_id"])
        status = "ON TRACK" if summary["percentage"] >= 50 else "IN PROGRESS"
        update_dashboard(user["sheet_id"], summary["percentage"], status)
        await update.message.reply_text(
            f"✅ *{topic}* marked DONE!\n\n"
            f"📊 Progress: *{summary['percentage']}%* ({summary['done']}/{summary['total']} topics)\n\n"
            "Keep it up! 🔥",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("done: %s", exc)
        await update.message.reply_text("❌ Error updating sheet. Try again.")


# ─── /test ────────────────────────────────────────────────────────────────────

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: `/test Chapter 3`", parse_mode="Markdown")
        return
    await update.message.reply_text(f"🧠 Generating quiz on *{topic}*…", parse_mode="Markdown")
    try:
        user = get_user(user_id)
        goal = user.get("goal", "General")
        subject = goal.split(" in ")[0].strip()
        questions = generate_mcq_test(topic, subject)
        set_quiz_state(user_id, {
            "active": True, "topic": topic,
            "questions": questions, "current_question": 0,
            "score": 0, "wrong_questions": [],
        })
        await _send_question(update, questions[0], 1, len(questions))
    except Exception as exc:
        logger.error("test: %s", exc)
        await update.message.reply_text("❌ Could not generate quiz. Try again.")


# ─── /progress ────────────────────────────────────────────────────────────────

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    user = get_user(user_id)
    await update.message.reply_text("📊 Building your progress report…")
    try:
        summary = get_progress_summary(user["sheet_id"])
        weak = get_weak_areas(user["sheet_id"])
        ai_report = generate_progress_report(
            user.get("name", "Student"), user.get("goal", ""),
            summary["done"], summary["total"],
            [w.get("Topic", "") for w in weak[:5]],
        )
        header = (
            f"📈 *Progress — {user.get('name')}*\n"
            f"🎯 {user.get('goal')}\n\n"
            f"✅ Done:    {summary['done']}/{summary['total']} ({summary['percentage']}%)\n"
            f"⏳ Pending: {summary['pending']} topics\n\n"
        )
        await update.message.reply_text(header + ai_report, parse_mode="Markdown")
    except Exception as exc:
        logger.error("progress: %s", exc)
        await update.message.reply_text("❌ Could not fetch progress.")


# ─── /stuck ───────────────────────────────────────────────────────────────────

async def stuck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: `/stuck Input Tax Credit`", parse_mode="Markdown")
        return
    user = get_user(user_id)
    try:
        update_weak_area(user["sheet_id"], topic)
        await update.message.reply_text(
            f"📝 *{topic}* added to Weak Areas tracker.\n\n"
            f"💡 Practice now: `/test {topic}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("stuck: %s", exc)
        await update.message.reply_text("❌ Error flagging topic.")


# ─── /reschedule ──────────────────────────────────────────────────────────────

async def reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    user = get_user(user_id)
    await update.message.reply_text("🔄 Analysing and reshuffling your plan…")
    try:
        pending = get_pending_topics(user["sheet_id"])
        weak = get_weak_areas(user["sheet_id"])
        end_dt = datetime.strptime(
            user.get("end_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
        )
        days_left = max(1, (end_dt - datetime.now()).days)
        days_missed = int(context.args[0]) if context.args else 0
        new_plan = reschedule_plan(
            pending, days_left, days_missed,
            [w.get("Topic", "") for w in weak[:5]],
        )
        await update.message.reply_text(
            f"✅ *Plan reshuffled!*\n\n"
            f"📋 {len(new_plan)} topics across {days_left} remaining days.\n"
            f"📊 {user.get('sheet_url', '')}\n\nUse /today to see updated targets.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("reschedule: %s", exc)
        await update.message.reply_text("❌ Could not reschedule. Try again.")


# ─── /report  ─────────────────────────────────────────────────────────────────

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await progress(update, context)


# ─── /help ────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *AI Study Partner — All Commands*\n\n"
        "*📚 Study Management*\n"
        "/start — Set up your study plan\n"
        "/today — Today's study targets\n"
        "/done \\[topic\\] — Mark topic complete\n"
        "/stuck \\[topic\\] — Flag a weak area\n"
        "/progress — Full progress report\n"
        "/reschedule — Reshuffle your plan\n"
        "/report — Weekly summary\n\n"
        "*🧠 AI Tools*\n"
        "/test \\[topic\\] — 5-question MCQ quiz\n"
        "/research \\[topic\\] — Deep research summary\n"
        "/explain \\[topic\\] — Plain-language explanation\n"
        "/compare \\[A\\] vs \\[B\\] — Compare two concepts\n"
        "/mnemonic \\[topic\\] — Memory trick\n"
        "/slides \\[topic\\] — Generate Gamma slide deck\n\n"
        "*📁 Your Material*\n"
        "/upload \\[subject\\] — Upload a PDF to NotebookLM\n"
        "/ask \\[question\\] — Ask from your uploaded material\n"
        "/podcast \\[subject\\] — Generate audio overview\n\n"
        "*⚙️ Settings*\n"
        "/settings — Change briefing time, alerts & more\n"
        "/help — Show this message\n\n"
        "💬 *Or just chat naturally:*\n"
        "• 'I finished Chapter 3'\n"
        "• 'Quiz me on GST basics'\n"
        "• 'I missed 3 days, help'",
        parse_mode="Markdown",
    )


# ─── Natural language dispatcher ─────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user = get_user(user_id)

    # 1. Onboarding
    if not user or user.get("onboarding_step") != "complete":
        await _handle_onboarding(update, context, user_id, text, user)
        return

    # 2. Active quiz
    quiz = get_quiz_state(user_id)
    if quiz and quiz.get("active"):
        await _handle_quiz_answer(update, user_id, text, quiz)
        return

    # 3. Awaiting settings input (e.g. briefing time typed by user)
    awaiting = user.get("awaiting_setting")
    if awaiting:
        await _handle_setting_input(update, context, user_id, text, awaiting)
        return

    # 4. NLP route
    result = await route_message(text)
    intent = result.get("intent", "UNKNOWN")
    topic  = result.get("topic")

    if intent == "DONE" and topic:
        context.args = topic.split(); await done(update, context)
    elif intent == "STUCK" and topic:
        context.args = topic.split(); await stuck(update, context)
    elif intent == "TODAY":
        await today(update, context)
    elif intent == "TEST" and topic:
        context.args = topic.split(); await test(update, context)
    elif intent == "PROGRESS":
        await progress(update, context)
    elif intent == "RESCHEDULE":
        await reschedule(update, context)
    elif intent == "REPORT":
        await report(update, context)
    else:
        await update.message.reply_text(
            "I'm not sure what you mean. Try /help to see all commands."
        )


# ─── Onboarding ───────────────────────────────────────────────────────────────

async def _handle_onboarding(update, context, user_id: int,
                               text: str, user: Optional[dict]) -> None:
    step = (user or {}).get("onboarding_step", "awaiting_name")

    if step == "awaiting_name":
        update_user(user_id, {"name": text.strip(), "onboarding_step": "awaiting_goal"})
        await update.message.reply_text(
            f"Great to meet you, *{text.strip()}*! 🎉\n\n"
            "What's your study goal?\n\n"
            "Examples:\n"
            "• CA Inter GST in 20 days\n"
            "• Python programming in 30 days\n"
            "• Class 12 Physics in 15 days",
            parse_mode="Markdown",
        )

    elif step == "awaiting_goal":
        update_user(user_id, {"goal": text.strip(), "onboarding_step": "awaiting_end_date"})
        await update.message.reply_text(
            f"🎯 Goal set: *{text.strip()}*\n\n"
            "Enter your target completion date:\n_(e.g. 2026-06-27 or 27 June 2026)_",
            parse_mode="Markdown",
        )

    elif step == "awaiting_end_date":
        end_date = _parse_date(text.strip())
        if not end_date:
            await update.message.reply_text(
                "⚠️ Couldn't parse that date. Try `2026-06-27` or `27 June 2026`.",
                parse_mode="Markdown",
            )
            return

        user_data = get_user(user_id) or {}
        update_user(user_id, {"end_date": end_date, "onboarding_step": "creating_plan"})
        await update.message.reply_text(
            "⚙️ Creating your personalised study plan and Google Sheet…\n"
            "This takes about 30-60 seconds — please wait! ⏳"
        )
        name = user_data.get("name", "Student")
        goal = user_data.get("goal", "Study Goal")
        start_date = datetime.now().strftime("%Y-%m-%d")

        # Step 1 — AI study plan
        try:
            plan = create_study_plan(name, goal, start_date, end_date)
        except Exception as exc:
            logger.error("Gemini plan creation failed: %s", exc, exc_info=True)
            update_user(user_id, {"onboarding_step": "awaiting_end_date"})
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                msg = (
                    "⏳ *AI is rate-limited* (Gemini free-tier quota hit).\n\n"
                    "• Wait ~1 minute and re-enter your date to retry.\n"
                    "• If it keeps failing, the *daily* free limit is used up — "
                    "enable billing on your Google Cloud project (Flash costs ~cents) "
                    "or try again tomorrow.\n"
                    "• Or switch to a lighter model via the `GEMINI_MODEL` env var "
                    "(e.g. `gemini-2.5-flash-lite`)."
                )
            else:
                msg = (
                    f"❌ *Gemini error:*\n`{err[:300]}`\n\n"
                    "Re-enter your target date to retry."
                )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # Step 2 — Google Sheet
        try:
            sheet_id, sheet_url = create_study_sheet(name, goal, start_date, end_date)
            write_study_plan(sheet_id, plan)
        except Exception as exc:
            logger.error("Google Sheets setup failed: %s", exc, exc_info=True)
            update_user(user_id, {"onboarding_step": "awaiting_end_date"})
            err = str(exc)
            low = err.lower()
            if "storagequota" in low or "storage quota" in low:
                msg = (
                    "❌ *Sheet failed — service accounts have no Drive storage.*\n\n"
                    "On a personal Gmail this can't be fixed with a folder — Google "
                    "blocks it by design.\n\n"
                    "*Real fix (free, 5 min):* let the bot use YOUR Google account.\n"
                    "1. On your computer, run `generate_oauth_token.py`\n"
                    "2. It prints a `GOOGLE_OAUTH_TOKEN` value\n"
                    "3. Add that in Render → Environment → Manual Deploy\n\n"
                    "Step-by-step is in the README. Then re-enter your target date."
                )
            elif "disabled" in low or "has not been used" in low or "service_disabled" in low:
                msg = (
                    "❌ *Sheet failed — an API is not enabled yet.*\n\n"
                    "Enable *both* in Google Cloud Console → APIs & Services → Library:\n"
                    "• Google Sheets API\n• Google Drive API\n\n"
                    "Wait 2-3 min after enabling, then re-enter your target date."
                )
            else:
                msg = (
                    f"❌ *Sheets error:*\n`{err[:400]}`\n\n"
                    "Re-enter your target date to retry."
                )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        update_user(user_id, {
            "sheet_id": sheet_id,
            "sheet_url": sheet_url,
            "start_date": start_date,
            "briefing_time": "08:00",
            "inactivity_mode": "2days",
            "onboarding_step": "complete",
        })

        # Schedule per-user jobs immediately
        schedule_user_briefing(context.application, user_id, "08:00")
        schedule_user_inactivity(context.application, user_id, "2days")

        await update.message.reply_text(
            f"🎉 *All set, {name}!*\n\n"
            f"📋 Study plan: *{len(plan)} days*\n"
            f"📊 Google Sheet: {sheet_url}\n\n"
            "I'll send you a briefing every morning at 8:00 AM.\n"
            "Change this anytime with /settings\n\n"
            "Use /today to see your first targets! 🚀",
            parse_mode="Markdown",
        )


# ─── Settings text input ──────────────────────────────────────────────────────

async def _handle_setting_input(update, context, user_id: int,
                                 text: str, setting_type: str) -> None:
    if setting_type == "briefing_time":
        try:
            parts = text.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            assert 0 <= h <= 23 and 0 <= m <= 59
            time_str = f"{h:02d}:{m:02d}"
        except Exception:
            await update.message.reply_text(
                "⚠️ Invalid format. Use HH:MM (e.g. `07:30` or `18:00`)",
                parse_mode="Markdown",
            )
            return
        update_user(user_id, {"briefing_time": time_str, "awaiting_setting": None})
        schedule_user_briefing(context.application, user_id, time_str)
        await update.message.reply_text(
            f"✅ Daily briefing updated to *{time_str}* ⏰\n"
            "I'll send you a morning message at this time every day!\n\n"
            "Use /settings to manage all preferences.",
            parse_mode="Markdown",
        )
    else:
        update_user(user_id, {"awaiting_setting": None})
        await update.message.reply_text("Setting update cancelled.")


# ─── Quiz answer ──────────────────────────────────────────────────────────────

async def _handle_quiz_answer(update, user_id: int, text: str, quiz: dict) -> None:
    answer = text.strip().upper()
    if answer not in ("A", "B", "C", "D"):
        await update.message.reply_text("Please reply with A, B, C, or D.")
        return

    questions = quiz["questions"]
    idx = quiz["current_question"]
    q = questions[idx]
    correct = q["correct_answer"].upper()

    if answer == correct:
        quiz["score"] += 1
        feedback = f"✅ *Correct!*\n_{q.get('explanation', '')}_"
    else:
        quiz["wrong_questions"].append(q["question"][:60])
        feedback = f"❌ *Wrong.* Correct: *{correct}*\n_{q.get('explanation', '')}_"

    quiz["current_question"] += 1
    await update.message.reply_text(feedback, parse_mode="Markdown")

    if quiz["current_question"] < len(questions):
        set_quiz_state(user_id, quiz)
        await _send_question(
            update, questions[quiz["current_question"]],
            quiz["current_question"] + 1, len(questions),
        )
    else:
        score, total = quiz["score"], len(questions)
        pct = score / total * 100
        msg = (
            f"🏆 *Quiz Complete!*\n\nTopic: {quiz['topic']}\n"
            f"Score: *{score}/{total}* ({pct:.0f}%)\n\n"
        )
        msg += (
            "🌟 Excellent — topic mastered!" if pct >= 80
            else "👍 Good — review a few more points." if pct >= 60
            else "📚 Needs practice. Use /stuck to flag this topic."
        )
        user = get_user(user_id)
        if user and user.get("sheet_id"):
            try:
                add_test_result(user["sheet_id"], quiz["topic"], score, total, quiz["wrong_questions"])
                if pct < 60:
                    update_weak_area(user["sheet_id"], quiz["topic"], f"{score}/{total}")
            except Exception as exc:
                logger.warning("Could not save test result: %s", exc)
        set_quiz_state(user_id, None)
        await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _send_question(update, q: dict, num: int, total: int) -> None:
    opts = q.get("options", {})
    await update.message.reply_text(
        f"❓ *Question {num}/{total}*\n\n{q['question']}\n\n"
        f"A) {opts.get('A', '')}\n"
        f"B) {opts.get('B', '')}\n"
        f"C) {opts.get('C', '')}\n"
        f"D) {opts.get('D', '')}\n\n"
        "_Reply with A, B, C, or D_",
        parse_mode="Markdown",
    )


def _parse_date(raw: str) -> Optional[str]:
    year = datetime.now().year
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    for fmt in ("%d %B", "%d %b"):
        try:
            return datetime.strptime(f"{raw} {year}", fmt + " %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None
