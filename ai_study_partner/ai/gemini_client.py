"""
All Gemini AI calls — uses the current google-genai SDK (replaces deprecated google-generativeai).
Default model: gemini-2.5-flash (override with GEMINI_MODEL).
If a model is retired (404) or rate-limited (429), the bot automatically falls
back through a list of models so a single model change never breaks everything.
"""
import json
import logging
import os
import time

from google import genai as _genai

logger = logging.getLogger(__name__)

# Preferred model (override via GEMINI_MODEL). The bot automatically falls back
# through the list below if a model is unavailable (404) or rate-limited (429),
# so a retired model never takes the whole bot down.
_PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]
_MAX_RETRIES = 3

_client: "_genai.Client | None" = None
_working_model: "str | None" = None  # cached once a model responds successfully


def _get_client() -> "_genai.Client":
    global _client
    if _client is None:
        _client = _genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _is_rate_limit(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def _is_model_unavailable(exc: Exception) -> bool:
    s = str(exc).lower()
    return "404" in s or "not_found" in s or "not available" in s or "is not found" in s


def _is_transient(exc: Exception) -> bool:
    s = str(exc)
    return "500" in s or "INTERNAL" in s or "503" in s or "502" in s


def _ordered_models() -> list:
    out, seen = [], set()
    for m in [_working_model, _PRIMARY_MODEL, *_FALLBACK_MODELS]:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _generate(prompt: str) -> str:
    global _working_model
    last_exc: "Exception | None" = None
    for model in _ordered_models():
        for attempt in range(_MAX_RETRIES):
            try:
                resp = _get_client().models.generate_content(model=model, contents=prompt)
                _working_model = model  # remember the model that worked
                return resp.text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if _is_rate_limit(exc):
                    if attempt < _MAX_RETRIES - 1:
                        wait = 3 * (attempt + 1)  # 3s, then 6s
                        logger.warning("Gemini %s rate-limited — retry in %ss", model, wait)
                        time.sleep(wait)
                        continue
                    logger.warning("Gemini %s still limited — trying next model", model)
                    break  # next model has a separate quota bucket
                if _is_transient(exc):
                    if attempt < _MAX_RETRIES - 1:
                        wait = 5 * (attempt + 1)  # 5s, then 10s
                        logger.warning("Gemini %s 500/502/503 — retry in %ss", model, wait)
                        time.sleep(wait)
                        continue
                    logger.warning("Gemini %s still returning server error — trying next model", model)
                    break
                if _is_model_unavailable(exc):
                    logger.warning("Gemini %s unavailable — trying next model", model)
                    break  # model retired — try the next one
                raise  # genuine error — surface immediately
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
