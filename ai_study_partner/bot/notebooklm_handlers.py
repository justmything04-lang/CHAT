"""
NotebookLM integration via notebooklm-py (unofficial).
Falls back to Gemini Files API automatically if the library is unavailable or fails.

Commands: /upload /ask /podcast
"""
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from state.session import get_user, is_onboarded, update_user

logger = logging.getLogger(__name__)

_NLM_AVAILABLE = False
try:
    from notebooklm import NotebookLMClient
    _NLM_AVAILABLE = True
except ImportError:
    logger.warning("notebooklm-py not installed — will use Gemini fallback for /upload /ask /podcast")


# ─── /upload ──────────────────────────────────────────────────────────────────

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    subject = " ".join(context.args) if context.args else "General"

    if not update.message.document:
        await update.message.reply_text(
            "📎 Send a PDF file with this command.\n"
            "Example: send your PDF and type `/upload GST Chapter 3` in the caption.",
            parse_mode="Markdown",
        )
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("⚠️ Only PDF files are supported.")
        return

    await update.message.reply_text(f"📥 Downloading and uploading *{doc.file_name}*…", parse_mode="Markdown")

    try:
        file = await doc.get_file()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            pdf_path = tmp.name

        if _NLM_AVAILABLE:
            nb_id = await _nlm_upload(pdf_path, subject)
            user = get_user(user_id)
            notebooks = user.get("notebooklm_notebooks", {})
            notebooks[subject] = nb_id
            update_user(user_id, {"notebooklm_notebooks": notebooks})
            await update.message.reply_text(
                f"✅ *{doc.file_name}* uploaded to NotebookLM!\n"
                f"Subject notebook: *{subject}*\n\n"
                "Use `/ask [your question]` to query it.",
                parse_mode="Markdown",
            )
        else:
            # Fallback: store file path for Gemini
            user = get_user(user_id)
            pdfs = user.get("local_pdfs", {})
            pdfs[subject] = pdf_path
            update_user(user_id, {"local_pdfs": pdfs})
            await update.message.reply_text(
                f"✅ *{doc.file_name}* stored for subject *{subject}*.\n"
                "_(Using Gemini fallback — NotebookLM not available)_\n\n"
                "Use `/ask [question]` to query your material.",
                parse_mode="Markdown",
            )
    except Exception as exc:
        logger.error("upload failed: %s", exc)
        await update.message.reply_text("❌ Upload failed. Please try again.")


async def _nlm_upload(pdf_path: str, subject: str) -> str:
    async with NotebookLMClient.from_storage(
        storage_path=os.getenv("NOTEBOOKLM_STORAGE_PATH", "./notebooklm_session/")
    ) as client:
        nb = await client.notebooks.create(f"{subject}_notebook")
        await client.sources.add_file(nb.id, pdf_path, wait=True)
        return nb.id


# ─── /ask ─────────────────────────────────────────────────────────────────────

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("Usage: `/ask What is the threshold for GST registration?`", parse_mode="Markdown")
        return

    user = get_user(user_id)
    await update.message.reply_text(f"🤔 Searching your study material for: _{question}_", parse_mode="Markdown")

    try:
        if _NLM_AVAILABLE and user.get("notebooklm_notebooks"):
            nb_id = next(iter(user["notebooklm_notebooks"].values()))
            answer = await _nlm_ask(nb_id, question)
        else:
            answer = await _gemini_ask(user, question)

        await update.message.reply_text(
            f"📚 *Answer from your material:*\n\n{answer}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("ask failed: %s", exc)
        await update.message.reply_text("❌ Could not answer. Upload your material first with /upload.")


async def _nlm_ask(nb_id: str, question: str) -> str:
    async with NotebookLMClient.from_storage(
        storage_path=os.getenv("NOTEBOOKLM_STORAGE_PATH", "./notebooklm_session/")
    ) as client:
        result = await client.chat.ask(nb_id, question)
        return result.answer


async def _gemini_ask(user: dict, question: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.0-flash")
    pdfs = user.get("local_pdfs", {})
    if pdfs:
        pdf_path = next(iter(pdfs.values()))
        sample = genai.upload_file(path=pdf_path)
        resp = model.generate_content([sample, question])
        return resp.text.strip()
    # No PDF — answer from general knowledge
    resp = model.generate_content(
        f"Answer this study question concisely for a student:\n{question}"
    )
    return resp.text.strip()


# ─── /podcast ─────────────────────────────────────────────────────────────────

async def podcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_onboarded(user_id):
        await update.message.reply_text("Please /start first.")
        return

    subject = " ".join(context.args) if context.args else ""
    if not subject:
        await update.message.reply_text("Usage: `/podcast GST Chapter 3`", parse_mode="Markdown")
        return

    if not _NLM_AVAILABLE:
        await update.message.reply_text(
            "⚠️ Audio podcast requires the NotebookLM library.\n"
            "As a fallback, use `/research` for a text summary instead.",
        )
        return

    user = get_user(user_id)
    notebooks = user.get("notebooklm_notebooks", {})
    if subject not in notebooks and not notebooks:
        await update.message.reply_text(
            f"No notebook found for *{subject}*. Upload a PDF first with `/upload {subject}`",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(f"🎙️ Generating audio overview for *{subject}*… (this takes 1-2 min)", parse_mode="Markdown")

    try:
        nb_id = notebooks.get(subject) or next(iter(notebooks.values()))
        mp3_path = await _nlm_podcast(nb_id, subject)
        with open(mp3_path, "rb") as audio:
            await update.message.reply_audio(
                audio=audio,
                title=f"AI Study Partner — {subject}",
                performer="NotebookLM Audio Overview",
            )
    except Exception as exc:
        logger.error("podcast failed: %s", exc)
        await update.message.reply_text("❌ Podcast generation failed. Try `/research` for a text summary.")


async def _nlm_podcast(nb_id: str, subject: str) -> str:
    async with NotebookLMClient.from_storage(
        storage_path=os.getenv("NOTEBOOKLM_STORAGE_PATH", "./notebooklm_session/")
    ) as client:
        status = await client.artifacts.generate_audio_overview(nb_id)
        await client.artifacts.wait_for_completion(nb_id, status.task_id)
        out_path = f"/tmp/{subject.replace(' ', '_')}_overview.mp3"
        await client.artifacts.download_audio(nb_id, output_path=out_path)
        return out_path
