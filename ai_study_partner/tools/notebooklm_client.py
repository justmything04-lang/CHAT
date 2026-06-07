"""
NotebookLM wrapper with Gemini fallback.
Import and use `nlm_upload`, `nlm_ask`, `nlm_podcast` from here.
"""
import logging
import os

logger = logging.getLogger(__name__)

try:
    from notebooklm import NotebookLMClient as _NLMClient
    NLM_AVAILABLE = True
except ImportError:
    NLM_AVAILABLE = False
    logger.warning("notebooklm-py not installed — Gemini fallback active")


_STORAGE = lambda: os.getenv("NOTEBOOKLM_STORAGE_PATH", "./notebooklm_session/")


async def nlm_upload(pdf_path: str, subject: str) -> str:
    """Upload PDF to NotebookLM. Returns notebook ID."""
    async with _NLMClient.from_storage(storage_path=_STORAGE()) as client:
        nb = await client.notebooks.create(f"{subject}_notebook")
        await client.sources.add_file(nb.id, pdf_path, wait=True)
        return nb.id


async def nlm_ask(nb_id: str, question: str) -> str:
    async with _NLMClient.from_storage(storage_path=_STORAGE()) as client:
        result = await client.chat.ask(nb_id, question)
        return result.answer


async def nlm_podcast(nb_id: str, subject: str) -> str:
    """Generate audio overview. Returns local MP3 path."""
    async with _NLMClient.from_storage(storage_path=_STORAGE()) as client:
        status = await client.artifacts.generate_audio_overview(nb_id)
        await client.artifacts.wait_for_completion(nb_id, status.task_id)
        out = f"/tmp/{subject.replace(' ', '_')}_overview.mp3"
        await client.artifacts.download_audio(nb_id, output_path=out)
        return out


async def gemini_ask_pdf(pdf_path: str, question: str) -> str:
    """Fallback: answer question using Gemini Files API."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.0-flash")
    uploaded = genai.upload_file(path=pdf_path)
    resp = model.generate_content([uploaded, question])
    return resp.text.strip()
