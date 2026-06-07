"""
Fast two-pass intent router:
  1. Keyword scan (free, instant)
  2. Gemini fallback (only when keywords give no match)
"""
import logging
from ai.gemini_client import classify_intent

logger = logging.getLogger(__name__)

_KEYWORDS: dict[str, list[str]] = {
    "DONE":       ["finished", "completed", "done with", "studied", "covered", "read"],
    "STUCK":      ["confused", "stuck", "struggling", "don't understand", "not getting",
                   "difficult", "help with", "unable to"],
    "TODAY":      ["what should i", "what to study", "today's", "today plan",
                   "target for today", "study today"],
    "TEST":       ["test me", "quiz me", "mcq", "question on", "practice test",
                   "quiz on", "test on"],
    "PROGRESS":   ["how am i", "my progress", "percentage", "how much done",
                   "status", "how far"],
    "RESCHEDULE": ["missed", "behind", "delay", "reschedule", "adjust plan",
                   "skipped days", "i am late"],
    "REPORT":     ["weekly report", "report", "summary", "overview"],
}


async def route_message(message: str) -> dict:
    """Return {intent, topic, confidence}."""
    lower = message.lower()

    for intent, kws in _KEYWORDS.items():
        if any(kw in lower for kw in kws):
            topic = _extract_topic(message, intent)
            return {"intent": intent, "topic": topic, "confidence": 0.85}

    try:
        return classify_intent(message)
    except Exception as exc:
        logger.error("Gemini classify failed: %s", exc)
        return {"intent": "UNKNOWN", "topic": None, "confidence": 0.0}


def _extract_topic(message: str, intent: str) -> str | None:
    """Naive topic extraction: text after the trigger keyword."""
    triggers = {
        "DONE":  ["finished", "completed", "done with", "studied", "covered"],
        "STUCK": ["stuck on", "confused about", "struggling with", "help with"],
        "TEST":  ["test me on", "quiz me on", "test on", "quiz on", "question on"],
    }
    lower = message.lower()
    for trigger in triggers.get(intent, []):
        if trigger in lower:
            idx = lower.index(trigger) + len(trigger)
            remainder = message[idx:].strip(" ,.")
            return remainder if remainder else None
    return None
