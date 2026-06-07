"""
All Gemini AI calls are here.
Model: gemini-2.0-flash  (free-tier compatible; change to gemini-2.0-flash-lite if needed)
"""
import os
import json
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)
_MODEL_NAME = "gemini-2.0-flash"


def _model():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    return genai.GenerativeModel(_MODEL_NAME)


def _parse_json(text: str):
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


# ─── Public API ──────────────────────────────────────────────────────────────

def create_study_plan(student_name: str, goal: str, start_date: str, end_date: str) -> list:
    prompt = f"""You are an expert academic mentor.
Create a day-by-day study plan for this student as a JSON array.
Each element must have exactly these keys:
  day (int), date (YYYY-MM-DD), topic (str), subtopics (list[str]),
  estimated_hours (float), difficulty (EASY|MEDIUM|HARD), notes (str)

Be realistic. Include revision days. Mark difficult topics HARD.
Return ONLY valid JSON array — no explanation, no markdown.

Student: {student_name}
Goal: {goal}
Start: {start_date}
Target: {end_date}"""
    resp = _model().generate_content(prompt)
    return _parse_json(resp.text)


def generate_mcq_test(topic: str, subject: str = "General") -> list:
    prompt = f"""You are an expert examiner for {subject}.
Generate exactly 5 MCQ questions on: {topic}
Return ONLY a JSON array where each element has:
  question (str), options ({{A,B,C,D: str}}), correct_answer (A|B|C|D), explanation (str)
Exam-level difficulty. Return ONLY valid JSON — no markdown."""
    resp = _model().generate_content(prompt)
    return _parse_json(resp.text)


def evaluate_progress(user_message: str, plan_summary: str, todays_topics: str) -> dict:
    prompt = f"""You are a personal study mentor.
Student said: "{user_message}"
Today's target: {todays_topics}
Plan summary: {plan_summary}
Return JSON with keys:
  topics_done (list[str]), topics_struggled (list[str]),
  mood_detected (str), plan_adjustment_needed (bool), motivational_message (str)
Return ONLY valid JSON."""
    resp = _model().generate_content(prompt)
    return _parse_json(resp.text)


def generate_daily_briefing(name: str, goal: str, topics: str,
                             days_left: int, progress_pct: float, weak_areas: str) -> str:
    prompt = f"""You are an energetic study coach sending a morning briefing.
Student: {name} | Goal: {goal}
Today's topics: {topics}
Days remaining: {days_left} | Progress: {progress_pct:.1f}%
Weak areas: {weak_areas}
Write a SHORT motivating morning briefing (max 100 words). Use emojis. Be specific."""
    resp = _model().generate_content(prompt)
    return resp.text.strip()


def reschedule_plan(remaining_topics: list, days_left: int,
                    days_missed: int, weak_areas: list) -> list:
    prompt = f"""Student is behind schedule.
Remaining topics: {json.dumps(remaining_topics)}
Days left: {days_left} | Days missed: {days_missed}
Weak areas needing revision: {json.dumps(weak_areas)}
Redistribute topics into a new day-by-day plan.
Return ONLY valid JSON array with keys:
  day, date (YYYY-MM-DD), topic, subtopics (list), estimated_hours, difficulty, notes"""
    resp = _model().generate_content(prompt)
    return _parse_json(resp.text)


def classify_intent(message: str) -> dict:
    prompt = f"""Classify this student message into one intent:
DONE | STUCK | TODAY | TEST | PROGRESS | RESCHEDULE | REPORT | UNKNOWN

Message: "{message}"

Return JSON: {{"intent": "...", "topic": "extracted topic or null", "confidence": 0.0-1.0}}
Return ONLY valid JSON."""
    resp = _model().generate_content(prompt)
    try:
        return _parse_json(resp.text)
    except Exception:
        return {"intent": "UNKNOWN", "topic": None, "confidence": 0.0}


def generate_progress_report(name: str, goal: str, done: int,
                               total: int, weak_areas: list) -> str:
    prompt = f"""Generate a progress report for this student:
Name: {name} | Goal: {goal}
Progress: {done}/{total} topics completed ({round(done/total*100) if total else 0}%)
Weak areas: {json.dumps(weak_areas[:5])}
Write an honest but encouraging report with specific next-step advice.
Max 200 words. Use emojis."""
    resp = _model().generate_content(prompt)
    return resp.text.strip()
