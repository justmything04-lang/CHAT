"""
Gemini-powered deep research commands (replaces Genspark/Sparkpages):
  /research [topic]       — structured Sparkpage-style summary
  /explain  [topic]       — plain-language explanation, ≤150 words
  /compare  [A] vs [B]    — side-by-side concept comparison
  /mnemonic [topic]       — memory tricks / acronyms
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from ai.gemini_client import (
    deep_research, explain_concept, compare_concepts, generate_mnemonic,
)
from state.session import get_user, is_onboarded

logger = logging.getLogger(__name__)


def _args_or_prompt(context, update) -> str:
    return " ".join(context.args) if context.args else ""


async def research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = _args_or_prompt(context, update)
    if not topic:
        await update.message.reply_text("Usage: `/research Input Tax Credit`", parse_mode="Markdown")
        return

    user = get_user(user_id)
    goal = user.get("goal", "")
    exam_level = goal.split(" in ")[0] if " in " in goal else "exam"

    await update.message.reply_text(f"🔍 Deep-researching *{topic}*…", parse_mode="Markdown")
    try:
        result = deep_research(topic, exam_level)
        await update.message.reply_text(
            f"📖 *Deep Research: {topic}*\n\n{result}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("research failed: %s", exc)
        await update.message.reply_text("❌ Research failed. Try again.")


async def explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = _args_or_prompt(context, update)
    if not topic:
        await update.message.reply_text("Usage: `/explain Reverse Charge Mechanism`", parse_mode="Markdown")
        return

    await update.message.reply_text(f"💡 Explaining *{topic}*…", parse_mode="Markdown")
    try:
        result = explain_concept(topic)
        await update.message.reply_text(
            f"💡 *{topic}*\n\n{result}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("explain failed: %s", exc)
        await update.message.reply_text("❌ Explanation failed. Try again.")


async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    text = " ".join(context.args) if context.args else ""
    if " vs " not in text.lower():
        await update.message.reply_text(
            "Usage: `/compare CGST vs IGST`", parse_mode="Markdown"
        )
        return

    parts = text.lower().split(" vs ", 1)
    a, b = parts[0].strip(), parts[1].strip()
    await update.message.reply_text(f"⚖️ Comparing *{a}* vs *{b}*…", parse_mode="Markdown")
    try:
        result = compare_concepts(a, b)
        await update.message.reply_text(
            f"⚖️ *{a.upper()} vs {b.upper()}*\n\n{result}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("compare failed: %s", exc)
        await update.message.reply_text("❌ Comparison failed. Try again.")


async def mnemonic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return
    topic = _args_or_prompt(context, update)
    if not topic:
        await update.message.reply_text("Usage: `/mnemonic GST registration threshold`", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🧠 Generating memory trick for *{topic}*…", parse_mode="Markdown")
    try:
        result = generate_mnemonic(topic)
        await update.message.reply_text(
            f"🧠 *Memory Trick: {topic}*\n\n{result}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("mnemonic failed: %s", exc)
        await update.message.reply_text("❌ Failed to generate mnemonic. Try again.")
