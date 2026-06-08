"""
All Gemini AI calls — uses the current google-genai SDK (replaces deprecated google-generativeai).
Model: gemini-2.0-flash  (free-tier; swap to gemini-2.5-flash for better reasoning)
"""
import json
import logging
import os
import time

from google import genai as _genai

logger = logging.getLogger(__name__)
_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
_MAX_RETRIES = 3

_client: "_genai.Client | None" = None


def _get_client() -> "_genai.Client":
    global _client
    if _client is None:
        _client = _genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _is_rate_limit(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def _generate(prompt: str) -> str:
    last_exc: "Exception | None" = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = _get_client().models.generate_content(model=_MODEL, contents=prompt)
            return resp.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limit(exc) and attempt < _MAX_RETRIES - 1:
                wait = 3 * (attempt + 1)  # 3s, then 6s
                logger.warning("Gemini rate-limited — retrying in %ss", wait)
                time.sleep(wait)
                continue
            raise
    raise last_exc  # pragma: no cover


def _parse_json(text: str):
    text = text.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


# ─── Study Plan ───────────────────────────────────────────────────────────────

def create_study_plan(student_name: str, goal: str, start_date: str, end_date: str) -> list:
    prompt = (
        "You are an expert academic mentor.\n"
        "Create a day-by-day study plan as a JSON array. Each element must have:\n"
        "  day (int), date (YYYY-MM-DD), topic (str), subtopics (list[str]),\n"
        "  estimated_hours (float), difficulty (EASY|MEDIUM|HARD), notes (str)\n"
        "Be realistic. Include revision days. Return ONLY valid JSON — no markdown.\n\n"
        f"Student: {student_name}\nGoal: {goal}\nStart: {start_date}\nTarget: {end_date}"
    )
    return _parse_json(_generate(prompt))


# ─── MCQ Test ─────────────────────────────────────────────────────────────────

def generate_mcq_test(topic: str, subject: str = "General") -> list:
    prompt = (
        f"You are an expert examiner for {subject}.\n"
        f"Generate exactly 5 MCQ questions on: {topic}\n"
        "Return ONLY a JSON array. Each element:\n"
        '  {"question": str, "options": {"A": str, "B": str, "C": str, "D": str}, '
        '"correct_answer": "A"|"B"|"C"|"D", "explanation": str}\n'
        "Exam-level difficulty. Return ONLY valid JSON."
    )
    return _parse_json(_generate(prompt))


# ─── Progress Evaluation ──────────────────────────────────────────────────────

def evaluate_progress(user_message: str, plan_summary: str, todays_topics: str) -> dict:
    prompt = (
        f'Student said: "{user_message}"\n'
        f"Today's target: {todays_topics}\nPlan summary: {plan_summary}\n"
        "Return JSON:\n"
        '{"topics_done": [], "topics_struggled": [], '
        '"mood_detected": str, "plan_adjustment_needed": bool, "motivational_message": str}'
    )
    return _parse_json(_generate(prompt))


# ─── Daily Briefing ───────────────────────────────────────────────────────────

def generate_daily_briefing(name: str, goal: str, topics: str,
                             days_left: int, progress_pct: float, weak_areas: str) -> str:
    prompt = (
        f"You are an energetic study coach. Send a morning briefing.\n"
        f"Student: {name} | Goal: {goal}\n"
        f"Today: {topics} | Days left: {days_left} | Progress: {progress_pct:.1f}%\n"
        f"Weak areas: {weak_areas}\n"
        "Write a SHORT motivating briefing (max 100 words). Use emojis. Be specific."
    )
    return _generate(prompt).strip()


# ─── Reschedule ───────────────────────────────────────────────────────────────

def reschedule_plan(remaining: list, days_left: int, days_missed: int, weak_areas: list) -> list:
    prompt = (
        f"Student is behind. Remaining: {json.dumps(remaining)}\n"
        f"Days left: {days_left} | Missed: {days_missed} | Weak: {json.dumps(weak_areas)}\n"
        "Redistribute into a new day-by-day plan.\n"
        "Return ONLY valid JSON array with keys: day, date, topic, subtopics, estimated_hours, difficulty, notes"
    )
    return _parse_json(_generate(prompt))


# ─── Intent Classification ────────────────────────────────────────────────────

def classify_intent(message: str) -> dict:
    prompt = (
        "Classify this student message into one intent:\n"
        "DONE | STUCK | TODAY | TEST | PROGRESS | RESCHEDULE | REPORT | UNKNOWN\n\n"
        f'Message: "{message}"\n\n'
        'Return JSON: {"intent": "...", "topic": "extracted topic or null", "confidence": 0.0-1.0}'
    )
    try:
        return _parse_json(_generate(prompt))
    except Exception:
        return {"intent": "UNKNOWN", "topic": None, "confidence": 0.0}


# ─── Progress Report ──────────────────────────────────────────────────────────

def generate_progress_report(name: str, goal: str, done: int, total: int, weak_areas: list) -> str:
    pct = round(done / total * 100) if total else 0
    prompt = (
        f"Student: {name} | Goal: {goal}\n"
        f"Progress: {done}/{total} ({pct}%) | Weak areas: {json.dumps(weak_areas[:5])}\n"
        "Write an honest, encouraging report with specific next-step advice. Max 200 words. Use emojis."
    )
    return _generate(prompt).strip()


# ─── Deep Research ────────────────────────────────────────────────────────────

def deep_research(topic: str, exam_level: str = "exam") -> str:
    prompt = (
        f"You are an expert academic researcher for {exam_level} students.\n"
        f"Research: {topic}\n\n"
        "Return a structured summary with exactly these sections:\n"
        "📌 *OVERVIEW* — 3-sentence plain summary\n"
        "🔑 *KEY CONCEPTS* — 5 bullet points, one-line each\n"
        "❓ *COMMON EXAM QUESTIONS* — 3 likely questions with brief answers\n"
        "🧠 *MEMORY TRICK* — one mnemonic or shortcut\n"
        "⚠️ *COMMON MISTAKES* — 2 things students often get wrong\n\n"
        "Keep total under 400 words. Use simple language. Format for Telegram."
    )
    return _generate(prompt).strip()


def explain_concept(topic: str) -> str:
    prompt = (
        f"Explain '{topic}' in plain language for a student. "
        "Under 150 words. No jargon. Use a simple real-life example."
    )
    return _generate(prompt).strip()


def compare_concepts(a: str, b: str) -> str:
    prompt = (
        f"Compare '{a}' and '{b}' for a student.\n"
        "Format as a clear text comparison with:\n"
        f"• What is {a}?\n• What is {b}?\n"
        "• Key differences (3 points)\n• When to use each\n"
        "Keep it under 200 words. Simple language."
    )
    return _generate(prompt).strip()


def generate_mnemonic(topic: str) -> str:
    prompt = (
        f"Create a memory trick (mnemonic, acronym, or story) to remember: '{topic}'\n"
        "Make it catchy, simple, and exam-relevant. Under 100 words."
    )
    return _generate(prompt).strip()


# ─── Slides Outline (for Gamma deep link) ────────────────────────────────────

def generate_slides_outline(topic: str, goal: str = "") -> str:
    prompt = (
        f"Create a 10-slide presentation outline for a student studying: {topic}\n"
        f"Context: {goal}\n\n"
        "Format as plain text with slide titles and 2-3 bullet points each.\n"
        "Keep it concise — this text will be URL-encoded into a Gamma link.\n"
        "No special characters except basic punctuation. Under 600 words."
    )
    return _generate(prompt).strip()
