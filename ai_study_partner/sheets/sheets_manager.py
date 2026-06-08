"""
All Google Sheets read/write operations — gspread 6.x with service-account auth.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional  # noqa: F401

import gspread

from sheets.sheet_templates import (
    BOLD, PROGRESS_LOG_HEADERS, RESOURCES_HEADERS,
    SESSION_HEADERS, STUDY_PLAN_HEADERS, TAB_NAMES,
    TEST_RESULTS_HEADERS, WEAK_AREAS_HEADERS,
)

logger = logging.getLogger(__name__)


def _client() -> gspread.Client:
    creds_file = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    return gspread.service_account(filename=creds_file)


def _col(n: int) -> str:
    """1→A, 26→Z, 27→AA"""
    result = ""
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


# ─── Sheet creation ───────────────────────────────────────────────────────────

def create_study_sheet(student_name: str, goal: str,
                        start_date: str, end_date: str) -> tuple[str, str]:
    gc = _client()
    # Creating inside a user-owned folder (shared with the service account)
    # avoids the service-account "storageQuotaExceeded" error on personal Gmail.
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip() or None
    ss = gc.create(f"AI Study Partner — {student_name}", folder_id=folder_id)
    ss.share(None, perm_type="anyone", role="reader")

    # Share with the admin's real email so they can see/edit it. Never fatal —
    # a wrong/own-SA email must not break onboarding.
    admin_email = os.getenv("SHEET_SHARE_EMAIL", "").strip()
    if admin_email:
        try:
            ss.share(admin_email, perm_type="user", role="writer")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not share with SHEET_SHARE_EMAIL=%s: %s", admin_email, exc)

    ws_dash = ss.get_worksheet(0)
    ws_dash.update_title(TAB_NAMES[0])
    # Placeholder — real dashboard rebuilt after study plan is written
    ws_dash.update("A1", [["AI Study Partner — setting up…"]])

    for tab in TAB_NAMES[1:]:
        ss.add_worksheet(title=tab, rows=1000, cols=26)

    _setup_headers(ss.worksheet(TAB_NAMES[1]), STUDY_PLAN_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[2]), PROGRESS_LOG_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[3]), TEST_RESULTS_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[4]), WEAK_AREAS_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[5]), RESOURCES_HEADERS)
    _setup_headers(ss.worksheet(TAB_NAMES[6]), SESSION_HEADERS)

    return ss.id, ss.url


def _setup_headers(ws, headers: list):
    ws.append_row(headers)
    ws.format(f"A1:{_col(len(headers))}1", BOLD)


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
    return [r for r in ws.get_all_records()
            if str(r.get("Date", "")) == today and r.get("Status", "") != "DONE"]


def get_pending_topics(sheet_id: str) -> list:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    return [r for r in ws.get_all_records() if r.get("Status", "") != "DONE"]


def mark_topic_done(sheet_id: str, keyword: str) -> bool:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[1])
    all_values = ws.get_all_values()
    if not all_values:
        return False
    headers = all_values[0]
    try:
        tc = headers.index("Topic") + 1
        sc = headers.index("Status") + 1
    except ValueError:
        return False
    for i, row in enumerate(all_values[1:], start=2):
        if keyword.lower() in row[tc - 1].lower() and row[sc - 1] != "DONE":
            ws.update_cell(i, sc, "DONE")
            return True
    return False


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

def add_test_result(sheet_id: str, topic: str, score: int,
                    total: int, weak_questions: list) -> None:
    revision = "YES" if total and score / total < 0.6 else "NO"
    retest = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d") if revision == "YES" else ""
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[3])
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        topic, f"{score}/{total}",
        "; ".join(weak_questions[:3]),
        revision, retest,
    ])


# ─── Weak Areas ───────────────────────────────────────────────────────────────

def update_weak_area(sheet_id: str, topic: str, last_score: str = "") -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[4])
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        if topic.lower() in str(row.get("Topic", "")).lower():
            ws.update_cell(i, 2, int(row.get("Times Struggled", 0)) + 1)
            if last_score:
                ws.update_cell(i, 3, last_score)
            return
    ws.append_row([topic, 1, last_score, "HIGH", "Review textbook & practice problems"])


def get_weak_areas(sheet_id: str) -> list:
    gc = _client()
    return gc.open_by_key(sheet_id).worksheet(TAB_NAMES[4]).get_all_records()


# ─── Resources (Tab 6) ────────────────────────────────────────────────────────

def log_resource(sheet_id: str, res_type: str, topic: str,
                 link_or_file: str, created_by: str, used_for: str = "Revision") -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[5])
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        res_type, topic, link_or_file, created_by, used_for,
    ])


# ─── Summary / Dashboard ──────────────────────────────────────────────────────

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


def refresh_dashboard(sheet_id: str, user: dict) -> None:
    """Rebuild the visual Tab 1 dashboard from latest sheet data."""
    from sheets.dashboard_builder import rebuild_dashboard
    gc = _client()
    ss = gc.open_by_key(sheet_id)
    ws_dash = ss.worksheet(TAB_NAMES[0])

    summary    = get_progress_summary(sheet_id)
    weak       = get_weak_areas(sheet_id)
    resources  = ss.worksheet(TAB_NAMES[5]).get_all_records()

    # This week = next 7 days of pending + today's done
    plan = summary["study_plan"]
    today = datetime.now().strftime("%Y-%m-%d")
    week_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    week_topics = [r for r in plan if today <= str(r.get("Date", "")) <= week_end][:7]

    rebuild_dashboard(ws_dash, user, summary, week_topics, weak, resources[-6:])


def update_dashboard(sheet_id: str, progress_pct: float, status: str) -> None:
    gc = _client()
    ws = gc.open_by_key(sheet_id).worksheet(TAB_NAMES[0])
    today = datetime.now().strftime("%Y-%m-%d")
    for i, row in enumerate(ws.get_all_values(), start=1):
        if row[0] == "Overall Progress %":
            ws.update_cell(i, 2, f"{progress_pct:.1f}%")
        elif row[0] == "Last Active Date":
            ws.update_cell(i, 2, today)
        elif row[0] == "Status":
            ws.update_cell(i, 2, status)
