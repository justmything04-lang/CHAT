"""
All Google Sheets read/write operations.
Uses gspread 6.x with service-account auth.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional
import gspread
from sheets.sheet_templates import (
    TAB_NAMES, DASHBOARD_ROWS,
    STUDY_PLAN_HEADERS, PROGRESS_LOG_HEADERS,
    TEST_RESULTS_HEADERS, WEAK_AREAS_HEADERS, BOLD_FORMAT,
)

logger = logging.getLogger(__name__)


def _client() -> gspread.Client:
    """Return an authenticated gspread client."""
    creds_file = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    return gspread.service_account(filename=creds_file)


# ─── Sheet creation ───────────────────────────────────────────────────────────

def create_study_sheet(student_name: str, goal: str,
                        start_date: str, end_date: str) -> tuple[str, str]:
    """Create a fresh Google Sheet and return (sheet_id, sheet_url)."""
    gc = _client()
    ss = gc.create(f"AI Study Partner — {student_name}")

    # Make it viewable by anyone with the link
    ss.share(None, perm_type="anyone", role="reader")

    # Also give write access to the service account email so the bot can edit
    admin_email = os.getenv("SHEET_SHARE_EMAIL")
    if admin_email:
        ss.share(admin_email, perm_type="user", role="writer")

    # Rename the first tab and populate it
    ws_dash = ss.get_worksheet(0)
    ws_dash.update_title(TAB_NAMES[0])
    _setup_dashboard(ws_dash, student_name, goal, start_date, end_date)

    # Create remaining tabs
    for tab in TAB_NAMES[1:]:
        ss.add_worksheet(title=tab, rows=1000, cols=26)

    _setup_headers(ss.worksheet(TAB_NAMES[1]), STUDY_PLAN_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[2]), PROGRESS_LOG_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[3]), TEST_RESULTS_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[4]), WEAK_AREAS_HEADERS)

    return ss.id, ss.url


def _setup_dashboard(ws, student_name, goal, start_date, end_date):
    rows = [list(r) for r in DASHBOARD_ROWS]  # copy
    rows[1][1] = student_name
    rows[2][1] = goal
    rows[3][1] = start_date
    rows[4][1] = end_date
    rows[7][1] = start_date
    ws.update("A1", rows)
    ws.format("A1:B1", BOLD_FORMAT)
    ws.format(f"A2:A{len(rows)}", BOLD_FORMAT)


def _setup_headers(ws, headers: list):
    ws.append_row(headers)
    ws.format(f"A1:{_col_letter(len(headers))}1", BOLD_FORMAT)


def _col_letter(n: int) -> str:
    """Convert column number to letter (1→A, 26→Z, 27→AA)."""
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


# ─── Study Plan ───────────────────────────────────────────────────────────────

def write_study_plan(sheet_id: str, plan: list) -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    rows = []
    for item in plan:
        subtopics = ", ".join(item.get("subtopics") or [])
        rows.append([
            item.get("day", ""),
            item.get("date", ""),
            item.get("topic", ""),
            subtopics,
            item.get("estimated_hours", 1),
            "PENDING",
            item.get("difficulty", "MEDIUM"),
            item.get("notes", ""),
            "NO",
        ])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")


def get_todays_topics(sheet_id: str) -> list:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        r for r in ws.get_all_records()
        if str(r.get("Date", "")) == today and r.get("Status", "") != "DONE"
    ]


def mark_topic_done(sheet_id: str, topic_keyword: str) -> bool:
    """Mark the first matching PENDING topic as DONE. Returns True if found."""
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    all_values = ws.get_all_values()
    if not all_values:
        return False
    headers = all_values[0]
    try:
        topic_col = headers.index("Topic") + 1
        status_col = headers.index("Status") + 1
    except ValueError:
        return False

    for i, row in enumerate(all_values[1:], start=2):
        if (topic_keyword.lower() in row[topic_col - 1].lower()
                and row[status_col - 1] != "DONE"):
            ws.update_cell(i, status_col, "DONE")
            return True
    return False


def get_pending_topics(sheet_id: str) -> list:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    return [r for r in ws.get_all_records() if r.get("Status", "") != "DONE"]


# ─── Progress Log ─────────────────────────────────────────────────────────────

def log_progress(sheet_id: str, topics_done: list, struggle_areas: list,
                 ai_feedback: str, plan_adjusted: bool) -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[2])
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        ", ".join(topics_done),
        ", ".join(struggle_areas),
        "",
        ai_feedback[:500],
        "YES" if plan_adjusted else "NO",
    ])


# ─── Test Results ─────────────────────────────────────────────────────────────

def add_test_result(sheet_id: str, topic: str, score: int, total: int,
                    weak_questions: list) -> None:
    revision_needed = "YES" if total > 0 and score / total < 0.6 else "NO"
    retest_date = ""
    if revision_needed == "YES":
        from datetime import timedelta
        retest_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[3])
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        topic,
        f"{score}/{total}",
        "; ".join(weak_questions[:3]),
        revision_needed,
        retest_date,
    ])


# ─── Weak Areas ───────────────────────────────────────────────────────────────

def update_weak_area(sheet_id: str, topic: str, last_score: str = "") -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[4])
    records = ws.get_all_records()

    for i, row in enumerate(records, start=2):
        if topic.lower() in str(row.get("Topic", "")).lower():
            count = int(row.get("Times Struggled", 0)) + 1
            ws.update_cell(i, 2, count)
            if last_score:
                ws.update_cell(i, 3, last_score)
            return

    ws.append_row([topic, 1, last_score, "HIGH", "Review textbook & practice problems"])


def get_weak_areas(sheet_id: str) -> list:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[4])
    return ws.get_all_records()


# ─── Dashboard / Summary ──────────────────────────────────────────────────────

def get_progress_summary(sheet_id: str) -> dict:
    gc = _client()
    plan = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1]).get_all_records()
    total = len(plan)
    done = sum(1 for r in plan if r.get("Status") == "DONE")
    return {
        "total": total,
        "done": done,
        "pending": total - done,
        "percentage": round(done / total * 100, 1) if total else 0.0,
        "study_plan": plan,
    }


def update_dashboard(sheet_id: str, progress_pct: float, status: str) -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[0])
    all_values = ws.get_all_values()
    today = datetime.now().strftime("%Y-%m-%d")
    for i, row in enumerate(all_values, start=1):
        if row[0] == "Overall Progress %":
            ws.update_cell(i, 2, f"{progress_pct:.1f}%")
        elif row[0] == "Last Active Date":
            ws.update_cell(i, 2, today)
        elif row[0] == "Status":
            ws.update_cell(i, 2, status)
