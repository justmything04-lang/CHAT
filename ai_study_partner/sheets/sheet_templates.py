"""Tab names, column headers, and colour constants for all 7 tabs."""

TAB_NAMES = [
    "DASHBOARD",    # Tab 1 — visual, rebuilt by bot
    "STUDY_PLAN",   # Tab 2
    "PROGRESS_LOG", # Tab 3
    "TEST_RESULTS", # Tab 4
    "WEAK_AREAS",   # Tab 5
    "RESOURCES",    # Tab 6
    "SESSION",      # Tab 7 — meta / session data (used by GSheet storage backend)
]

# ── Column headers ─────────────────────────────────────────────────────────────
STUDY_PLAN_HEADERS    = ["Day No.", "Date", "Topic", "Subtopics",
                          "Est. Hours", "Status", "Difficulty", "Notes", "Revised?"]
PROGRESS_LOG_HEADERS  = ["Date", "Topics Covered", "Struggle Areas",
                          "Time Spent", "AI Feedback", "Plan Adjusted?"]
TEST_RESULTS_HEADERS  = ["Date", "Topic", "Score", "Weak Questions",
                          "Revision Needed", "Retest Date"]
WEAK_AREAS_HEADERS    = ["Topic", "Times Struggled", "Last Test Score",
                          "Priority", "Extra Resources"]
RESOURCES_HEADERS     = ["Date", "Type", "Topic", "Link / File",
                          "Created By", "Used For"]
SESSION_HEADERS       = ["user_id", "data"]

# ── Cell colours (RGB 0-1 floats) ─────────────────────────────────────────────
COLOR = {
    "header_dark": {"red": 0.07, "green": 0.07, "blue": 0.18},   # dark navy
    "header_text": {"red": 1.0,  "green": 1.0,  "blue": 1.0},    # white
    "card_green":  {"red": 0.13, "green": 0.55, "blue": 0.30},   # done
    "card_blue":   {"red": 0.12, "green": 0.33, "blue": 0.70},   # today
    "card_amber":  {"red": 0.65, "green": 0.38, "blue": 0.05},   # at risk
    "card_red":    {"red": 0.65, "green": 0.10, "blue": 0.10},   # weak
    "card_teal":   {"red": 0.04, "green": 0.44, "blue": 0.45},   # neutral info
    "row_done":    {"red": 0.73, "green": 0.93, "blue": 0.75},   # light green
    "row_today":   {"red": 0.67, "green": 0.78, "blue": 0.97},   # light blue
    "row_pending": {"red": 0.93, "green": 0.93, "blue": 0.93},   # light grey
    "white":       {"red": 1.0,  "green": 1.0,  "blue": 1.0},
}

BOLD = {"textFormat": {"bold": True}}
WHITE_TEXT = {"textFormat": {"foregroundColor": COLOR["header_text"], "bold": True}}
