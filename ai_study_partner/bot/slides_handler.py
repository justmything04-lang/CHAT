"""
/slides command — Gamma deep-link strategy (no API key required).
Bot generates slide content via Gemini, encodes it into a Gamma URL,
sends an inline keyboard button so user opens a pre-filled editor in one click.
"""
import logging
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ai.gemini_client import generate_slides_outline
from sheets.sheets_manager import log_resource
from state.session import get_user, is_onboarded, update_user

logger = logging.getLogger(__name__)

_GAMMA_BASE = "https://gamma.app/create"
_DEFAULT_CARDS = 10


async def slides(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text(
            "Usage: `/slides GST Chapter 3 — Input Tax Credit`",
            parse_mode="Markdown",
        )
        return

    user = get_user(user_id)

    # One-time Gamma onboarding check
    if not user.get("gamma_logged_in"):
        await _gamma_onboarding(update, context, user_id, topic)
        return

    await _generate_and_send(update, context, user_id, user, topic)


async def _gamma_onboarding(update, context, user_id: int, pending_topic: str) -> None:
    update_user(user_id, {"gamma_pending_topic": pending_topic})
    await update.message.reply_text(
        "🎨 *First-time Gamma setup*\n\n"
        "Gamma is a free AI slide builder. The bot will send you a direct link — "
        "one click and your slides open pre-filled, ready to generate.\n\n"
        "*Step 1:* Do you have a free Gamma account?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, I have an account", callback_data="gamma:has_account"),
            InlineKeyboardButton("🔗 Create free account",   callback_data="gamma:create_account"),
        ]]),
    )


async def handle_gamma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "gamma:create_account":
        await query.message.reply_text(
            "👉 Sign up free at gamma.app — then come back and use /slides again!\n"
            "https://gamma.app"
        )
        return

    if data == "gamma:has_account":
        await query.message.edit_text(
            "*Step 2:* Are you logged into Gamma in your browser right now?\n\n"
            "_(The link only works if you're already logged in)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, I'm logged in", callback_data="gamma:logged_in"),
            ]]),
        )

    elif data == "gamma:logged_in":
        update_user(user_id, {"gamma_logged_in": True})
        user = get_user(user_id)
        pending = user.get("gamma_pending_topic", "")
        await query.message.edit_text(
            "🎉 *Gamma setup complete!*\n\n"
            "From now on every /slides command sends you a direct one-click link.\n"
            "No copy-paste. Ever.",
            parse_mode="Markdown",
        )
        if pending:
            context.args = pending.split()
            await _generate_and_send(query, context, user_id, user, pending)


async def _generate_and_send(update_or_query, context, user_id: int, user: dict, topic: str) -> None:
    msg_obj = (
        update_or_query.message
        if hasattr(update_or_query, "message")
        else update_or_query
    )

    await msg_obj.reply_text(f"🎨 Generating slide outline for *{topic}*…", parse_mode="Markdown")

    try:
        outline = generate_slides_outline(topic, user.get("goal", ""))
        encoded  = quote(outline, safe="")
        url      = f"{_GAMMA_BASE}?text={encoded}&cards={_DEFAULT_CARDS}"

        update_user(user_id, {"last_gamma_url": url})

        # Save to Google Sheet RESOURCES tab
        if user.get("sheet_id"):
            try:
                log_resource(user["sheet_id"], "SLIDES", topic, url, "AI-generated")
            except Exception as e:
                logger.warning("Could not log resource: %s", e)

        await msg_obj.reply_text(
            f"🎨 *Revision Slides Ready — {topic}*\n\n"
            "Your 10-slide deck has been prepared by AI.\n\n"
            "✅ Step 1: Make sure you are logged into *gamma.app* in your browser\n"
            "✅ Step 2: Click the button below\n"
            "✅ Step 3: Hit *Generate* — slides ready in 10 seconds!\n\n"
            "💾 Link saved to your Google Sheet → Resources tab",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 OPEN IN GAMMA →", url=url),
            ]]),
        )
    except Exception as exc:
        logger.error("Slides generation failed: %s", exc)
        await msg_obj.reply_text("❌ Could not generate slides. Please try again.")
