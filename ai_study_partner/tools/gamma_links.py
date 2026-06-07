"""
Gamma deep-link builder.
No API key needed — encodes AI-generated content into a direct Gamma URL.
User clicks while logged in → lands on pre-filled slide editor.
"""
import os
from urllib.parse import quote


def build_gamma_url(content: str, num_cards: int = 10) -> str:
    base  = os.getenv("GAMMA_BASE_URL", "https://gamma.app/create")
    cards = os.getenv("GAMMA_DEFAULT_CARDS", str(num_cards))
    return f"{base}?text={quote(content, safe='')}&cards={cards}"


def build_gamma_prompt_url(prompt: str) -> str:
    """Alternative: pre-fill the AI prompt field instead of raw text."""
    base = os.getenv("GAMMA_BASE_URL", "https://gamma.app/create")
    return f"{base}?prompt={quote(prompt, safe='')}"
