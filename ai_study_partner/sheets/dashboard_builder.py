"""
Builds the visual Tab 1 DASHBOARD.
Called whenever progress changes — clears and fully rebuilds.

Layout (rows 1-38):
  1-2   : Dark header banner — name + goal
  4-11  : 6 metric cards  (progress, streak, days left, status, topics, last test)
  13    : "THIS WEEK'S PLAN" section header
  14-21 : Up to 7 day rows — colour-coded DONE/TODAY/PENDING
  23    : "WEAK AREAS" header
  24-28 : Top 5 weak topics
  30    : "RESOURCES" header
  31-37 : Recent Gamma / NotebookLM / research links
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import gspread

from sheets.sheet_templates import COLOR, WHITE_TEXT

logger = logging.getLogger(__name__)

_W = 9  # sheet width in columns (A–I)


def _rgb(color_dict: dict) -> dict:
    return {"red": color_dict["red"], "green": color_dict["green"], "blue": color_dict["blue"]}


def _bg(color_key: str) -> dict:
    return {"backgroundColor": _rgb(COLOR[color_key])}


def _cell_fmt(bg_key: str, bold: bool = False, white_text: bool = False,
               font_size: int = 10, h_align: str = "CENTER") -> dict:
    fmt: dict = {
        "backgroundColor": _rgb(COLOR[bg_key]),
        "horizontalAlignment": h_align,
        "textFormat": {
            "bold": bold,
            "fontSize": font_size,
        },
    }
    if white_text:
        fmt["textFormat"]["foregroundColor"] = _rgb(COLOR["header_text"])
    return fmt


def rebuild_dashboard(ws: gspread.Worksheet, user: dict, summary: dict,
                       week_topics: list, weak_areas: list, resources: list) -> None:
    """Fully rebuild Tab 1 in one batch update."""
    ws.clear()

    name     = user.get("name", "Student")
    goal     = user.get("goal", "Study Goal")
    pct      = summary.get("percentage", 0)
    done     = summary.get("done", 0)
    total    = summary.get("total", 0)
    streak   = user.get("streak", 0)
    status   = user.get("study_status", "ON TRACK")

    end_str  = user.get("end_date", datetime.now().strftime("%Y-%m-%d"))
    try:
        days_left = max(0, (datetime.strptime(end_str, "%Y-%m-%d") - datetime.now()).days)
    except ValueError:
        days_left = 0

    last_test_score = user.get("last_test_score", "—")

    # ── 1. Build cell values (A1:I38) ────────────────────────────────────────
    grid: list[list] = [[""] * _W for _ in range(38)]

    # Header rows 0-1 (0-indexed)
    grid[0] = [f"🤖 AI Study Partner — {name}"] + [""] * (_W - 1)
    grid[1] = [goal] + [""] * (_W - 1)

    # Metric cards — row 3 (labels), row 4 (values)
    grid[3] = ["📊 Overall", "", "🔥 Streak", "", "📅 Days Left", "", "✅ Status", "", ""]
    grid[4] = [f"{pct:.0f}% complete", "", f"{streak} days", "",
               f"{days_left} days", "", status, "", ""]
    grid[5] = [""] * _W
    grid[6] = ["📚 Topics Done", "", "🎯 Next Up", "", "", "🧪 Last Test", "", "", ""]
    next_up = week_topics[0].get("Topic", "—") if week_topics else "—"
    grid[7] = [f"{done} / {total}", "", next_up, "", "", str(last_test_score), "", "", ""]

    # Section: This Week
    grid[9]  = ["📅 THIS WEEK'S PLAN"] + [""] * (_W - 1)
    grid[10] = ["Day", "Date", "Topic", "Subtopics", "Hours", "Status", "Difficulty", "", ""]

    for i, topic in enumerate(week_topics[:7]):
        r = 11 + i
        status_val = str(topic.get("Status", "PENDING"))
        grid[r] = [
            topic.get("Day No.", ""),
            topic.get("Date", ""),
            topic.get("Topic", ""),
            topic.get("Subtopics", ""),
            topic.get("Est. Hours", ""),
            status_val,
            topic.get("Difficulty", ""),
            "", "",
        ]

    # Section: Weak Areas
    grid[19] = ["⚠️ WEAK AREAS TRACKER"] + [""] * (_W - 1)
    grid[20] = ["Topic", "Times Struggled", "Last Score", "Priority", "", "", "", "", ""]
    for i, area in enumerate(weak_areas[:5]):
        r = 21 + i
        grid[r] = [
            area.get("Topic", ""),
            area.get("Times Struggled", ""),
            area.get("Last Test Score", ""),
            area.get("Priority", ""),
            "", "", "", "", "",
        ]

    # Section: Resources
    grid[27] = ["🔗 RECENT RESOURCES"] + [""] * (_W - 1)
    grid[28] = ["Date", "Type", "Topic", "Link / File", "", "", "", "", ""]
    for i, res in enumerate(resources[:6]):
        r = 29 + i
        grid[r] = [
            res.get("Date", ""),
            res.get("Type", ""),
            res.get("Topic", ""),
            res.get("Link / File", ""),
            "", "", "", "", "",
        ]

    # ── 2. Write values ────────────────────────────────────────────────────────
    ws.update("A1", grid, value_input_option="USER_ENTERED")

    # ── 3. Batch format ────────────────────────────────────────────────────────
    fmt_requests = []

    def _range_fmt(start_row: int, end_row: int, start_col: int, end_col: int,
                   bg_key: str, bold: bool = False, white_text: bool = False,
                   font_size: int = 10, h_align: str = "CENTER") -> dict:
        fmt = _cell_fmt(bg_key, bold, white_text, font_size, h_align)
        return {
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {"userEnteredFormat": fmt},
                "fields": "userEnteredFormat",
            }
        }

    # Header rows (dark navy, white text, large font)
    fmt_requests.append(_range_fmt(0, 2, 0, _W, "header_dark", bold=True, white_text=True, font_size=13))

    # Metric card rows
    card_bg = "card_green" if pct >= 70 else "card_amber" if pct >= 40 else "card_red"
    fmt_requests.append(_range_fmt(3, 8, 0, 2, card_bg, bold=True, white_text=True, font_size=11))
    fmt_requests.append(_range_fmt(3, 8, 2, 4, "card_teal", bold=True, white_text=True, font_size=11))
    fmt_requests.append(_range_fmt(3, 8, 4, 6, "card_blue", bold=True, white_text=True, font_size=11))
    status_bg = "card_green" if status == "ON TRACK" else "card_amber" if status == "AT RISK" else "card_red"
    fmt_requests.append(_range_fmt(3, 8, 6, _W, status_bg, bold=True, white_text=True, font_size=11))

    # Section header rows
    for row in [9, 19, 27]:
        fmt_requests.append(_range_fmt(row, row + 1, 0, _W, "header_dark", bold=True, white_text=True))

    # Column header rows
    for row in [10, 20, 28]:
        fmt_requests.append(_range_fmt(row, row + 1, 0, _W, "card_teal", bold=True, white_text=True))

    # Colour-code this week's rows by status
    for i, topic in enumerate(week_topics[:7]):
        r = 11 + i
        s = str(topic.get("Status", "PENDING")).upper()
        today_str = datetime.now().strftime("%Y-%m-%d")
        if s == "DONE":
            bg = "row_done"
        elif str(topic.get("Date", "")) == today_str:
            bg = "row_today"
        else:
            bg = "row_pending"
        fmt_requests.append(_range_fmt(r, r + 1, 0, _W, bg, h_align="LEFT"))

    ws.spreadsheet.batch_update({"requests": fmt_requests})

    # ── 4. Merge header cells ─────────────────────────────────────────────────
    merge_requests = []
    for row in [0, 1, 9, 19, 27]:
        merge_requests.append({
            "mergeCells": {
                "range": {"sheetId": ws.id, "startRowIndex": row, "endRowIndex": row + 1,
                           "startColumnIndex": 0, "endColumnIndex": _W},
                "mergeType": "MERGE_ALL",
            }
        })
    ws.spreadsheet.batch_update({"requests": merge_requests})

    logger.info("Dashboard rebuilt for %s — %s%%", name, pct)
