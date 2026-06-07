"""
All Telegram command and message handlers.
Onboarding state machine:  awaiting_name → awaiting_goal → awaiting_end_date → complete
"""
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from state.session import (
    get_user, update_user, is_onboarded,
    get_quiz_state, set_quiz_state,
)
from ai.gemini_client import (
    create_study_plan, generate_mcq_test, evaluate_progress,
    generate_progress_report, reschedule_plan,
)
from sheets.sheets_manager import (
    create_study_sheet, write_study_plan, get_todays_topics,
    mark_topic_done, log_progress, add_test_result, update_weak_area,
    get_weak_areas, get_progress_summary, update_dashboard,
    get_pending_topics,
)
from bot.nlp_router import route_message

logger = logging.getLogger(__name__)


# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user and user.get("onboarding_step") == "complete":
        await update.message.reply_text(
            f"Welcome back, *{user['name']}*! 👋\n\n"
            "Use /today for targets or /help for all commands.",
            parse_mode="Markdown",
        )
        return

    update_user(user_id, {"onboarding_step": "awaiting_name"})
    await update.message.reply_text(
        "🤖 *Welcome to AI Study Partner!*\n\n"
        "I'll create your personalized study plan, track your progress,\n"
        "quiz you, and keep you on track — all from this chat!\n\n"
        "Let's start. *What's your name?*",
        parse_mode="Markdown",
    )


# ─── /today ───────────────────────────────────────────────────────────────────

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first to set up your plan.")
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
        lines.append(
            f"  ⏱ {t.get('Est. Hours', 1)}h  |  📊 {t.get('Difficulty', 'MEDIUM')}\n"
        )
        try:
            total_h += float(t.get("Est. Hours", 0))
        except (ValueError, TypeError):
            pass

    lines.append(f"⏰ *Total: {total_h:.1f} hours*")
    lines.append("\nDone with a topic? Say _'I finished [topic]'_ or /done [topic]")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── /done ────────────────────────────────────────────────────────────────────

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Usage: `/done Chapter 3`", parse_mode="Markdown"
        )
        return

    user = get_user(user_id)
    try:
        found = mark_topic_done(user["sheet_id"], topic)
        if not found:
            await update.message.reply_text(
                f"⚠️ Could not find *{topic}* in your plan. "
                "Check /today for exact topic names.",
                parse_mode="Markdown",
            )
            return

        summary = get_progress_summary(user["sheet_id"])
        status = "ON TRACK" if summary["percentage"] >= 50 else "IN PROGRESS"
        update_dashboard(user["sheet_id"], summary["percentage"], status)

        await update.message.reply_text(
            f"✅ *{topic}* marked DONE!\n\n"
            f"📊 Progress: *{summary['percentage']}%*  "
            f"({summary['done']}/{summary['total']} topics)\n\n"
            "Keep it up! 🔥",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("mark_topic_done: %s", exc)
        await update.message.reply_text("❌ Error updating sheet. Please try again.")


# ─── /test ────────────────────────────────────────────────────────────────────

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Usage: `/test Chapter 3`", parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"🧠 Generating quiz on *{topic}*…", parse_mode="Markdown")

    try:
        user = get_user(user_id)
        goal = user.get("goal", "General")
        subject = goal.split(" in ")[0].strip()

        questions = generate_mcq_test(topic, subject)
        set_quiz_state(user_id, {
            "active": True,
            "topic": topic,
            "questions": questions,
            "current_question": 0,
            "score": 0,
            "wrong_questions": [],
        })
        await _send_question(update, questions[0], 1, len(questions))
    except Exception as exc:
        logger.error("generate_mcq_test: %s", exc)
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
        weak_names = [w.get("Topic", "") for w in weak[:5]]

        ai_report = generate_progress_report(
            user.get("name", "Student"),
            user.get("goal", ""),
            summary["done"],
            summary["total"],
            weak_names,
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
        await update.message.reply_text(
            "Usage: `/stuck Input Tax Credit`", parse_mode="Markdown"
        )
        return

    user = get_user(user_id)
    try:
        update_weak_area(user["sheet_id"], topic)
        await update.message.reply_text(
            f"📝 *{topic}* added to Weak Areas tracker.\n\n"
            "I'll prioritise this in your revision schedule.\n"
            f"💡 Practice now with `/test {topic}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("stuck: %s", exc)
        await update.message.reply_text("❌ Error updating weak areas.")


# ─── /reschedule ──────────────────────────────────────────────────────────────

async def reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    user = get_user(user_id)
    await update.message.reply_text("🔄 Analysing your plan and reshuffling…")

    try:
        pending = get_pending_topics(user["sheet_id"])
        weak = get_weak_areas(user["sheet_id"])
        weak_names = [w.get("Topic", "") for w in weak[:5]]

        end_dt = datetime.strptime(
            user.get("end_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
        )
        days_left = max(1, (end_dt - datetime.now()).days)
        days_missed = int(context.args[0]) if context.args else 0

        new_plan = reschedule_plan(pending, days_left, days_missed, weak_names)

        await update.message.reply_text(
            f"✅ *Plan reshuffled!*\n\n"
            f"📋 {len(new_plan)} topics redistributed across {days_left} remaining days.\n"
            f"📊 View your sheet: {user.get('sheet_url', '(see your Google Sheet)')}\n\n"
            "Use /today to see updated targets.",
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
        "/start — Set up your study plan\n"
        "/today — Get today's study targets\n"
        "/done \\[topic\\] — Mark a topic complete\n"
        "/test \\[topic\\] — Take a 5-question quiz\n"
        "/stuck \\[topic\\] — Flag a topic as difficult\n"
        "/progress — Full progress report\n"
        "/reschedule — Reshuffle your plan\n"
        "/report — Weekly summary\n"
        "/help — Show this message\n\n"
        "💬 *Or just chat naturally:*\n"
        "• 'I finished Chapter 3'\n"
        "• 'Quiz me on GST basics'\n"
        "• 'I'm confused about ITC'\n"
        "• 'What should I study today?'\n"
        "• 'I missed 3 days, help'",
        parse_mode="Markdown",
    )


# ─── Natural language dispatcher ─────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user = get_user(user_id)

    # Onboarding takes priority
    if not user or user.get("onboarding_step") != "complete":
        await _handle_onboarding(update, user_id, text, user)
        return

    # Quiz answer takes second priority
    quiz = get_quiz_state(user_id)
    if quiz and quiz.get("active"):
        await _handle_quiz_answer(update, user_id, text, quiz)
        return

    # NLP route
    result = await route_message(text)
    intent = result.get("intent", "UNKNOWN")
    topic = result.get("topic")

    if intent == "DONE" and topic:
        context.args = topic.split()
        await done(update, context)
    elif intent == "STUCK" and topic:
        context.args = topic.split()
        await stuck(update, context)
    elif intent == "TODAY":
        await today(update, context)
    elif intent == "TEST" and topic:
        context.args = topic.split()
        await test(update, context)
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


# ─── Onboarding state machine ─────────────────────────────────────────────────

async def _handle_onboarding(update, user_id: int, text: str, user: Optional[dict]) -> None:
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

        try:
            name = user_data.get("name", "Student")
            goal = user_data.get("goal", "Study Goal")
            start_date = datetime.now().strftime("%Y-%m-%d")

            plan = create_study_plan(name, goal, start_date, end_date)
            sheet_id, sheet_url = create_study_sheet(name, goal, start_date, end_date)
            write_study_plan(sheet_id, plan)

            update_user(user_id, {
                "sheet_id": sheet_id,
                "sheet_url": sheet_url,
                "start_date": start_date,
                "onboarding_step": "complete",
            })

            await update.message.reply_text(
                f"🎉 *All set, {name}!*\n\n"
                f"📋 Study plan: *{len(plan)} days*\n"
                f"📊 Google Sheet: {sheet_url}\n\n"
                "You can view your sheet anytime — the bot updates it automatically.\n\n"
                "Use /today to see your first targets! 🚀",
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Onboarding failed: %s", exc)
            update_user(user_id, {"onboarding_step": "awaiting_end_date"})
            await update.message.reply_text(
                "❌ Something went wrong creating your plan.\n"
                "Please re-enter your target date to try again."
            )


# ─── Quiz answer handler ──────────────────────────────────────────────────────

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
        feedback = (
            f"❌ *Wrong.* Correct answer: *{correct}*\n"
            f"_{q.get('explanation', '')}_"
        )

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
            f"🏆 *Quiz Complete!*\n\n"
            f"Topic: {quiz['topic']}\n"
            f"Score: *{score}/{total}* ({pct:.0f}%)\n\n"
        )
        msg += (
            "🌟 Excellent — topic mastered!" if pct >= 80
            else "👍 Good — review a few more points." if pct >= 60
            else "📚 Needs more practice. Use /stuck to flag this topic."
        )

        user = get_user(user_id)
        if user and user.get("sheet_id"):
            try:
                add_test_result(
                    user["sheet_id"], quiz["topic"],
                    score, total, quiz["wrong_questions"],
                )
                if pct < 60:
                    update_weak_area(user["sheet_id"], quiz["topic"], f"{score}/{total}")
            except Exception as exc:
                logger.warning("Could not save test result: %s", exc)

        set_quiz_state(user_id, None)
        await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _send_question(update, q: dict, num: int, total: int) -> None:
    opts = q.get("options", {})
    text = (
        f"❓ *Question {num}/{total}*\n\n"
        f"{q['question']}\n\n"
        f"A) {opts.get('A', '')}\n"
        f"B) {opts.get('B', '')}\n"
        f"C) {opts.get('C', '')}\n"
        f"D) {opts.get('D', '')}\n\n"
        "_Reply with A, B, C, or D_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def _parse_date(raw: str) -> Optional[str]:
    from datetime import datetime
    year = datetime.now().year
    formats_with_year = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y"]
    formats_no_year = ["%d %B", "%d %b", "%B %d"]

    for fmt in formats_with_year:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    for fmt in formats_no_year:
        try:
            return datetime.strptime(f"{raw} {year}", fmt + " %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None
