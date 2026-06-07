"""Column headers and tab names for the AI Study Partner Google Sheet."""

TAB_NAMES = ["DASHBOARD", "STUDY_PLAN", "PROGRESS_LOG", "TEST_RESULTS", "WEAK_AREAS"]

DASHBOARD_ROWS = [
    ["Field", "Value"],
    ["Student Name", ""],
    ["Goal", ""],
    ["Start Date", ""],
    ["Target Date", ""],
    ["Overall Progress %", "0%"],
    ["Current Streak (days)", "0"],
    ["Last Active Date", ""],
    ["Predicted Completion", ""],
    ["Status", "PENDING"],
]

STUDY_PLAN_HEADERS = [
    "Day No.", "Date", "Topic", "Subtopics",
    "Est. Hours", "Status", "Difficulty", "Notes", "Revised?",
]

PROGRESS_LOG_HEADERS = [
    "Date", "Topics Covered", "Struggle Areas",
    "Time Spent", "AI Feedback", "Plan Adjusted?",
]

TEST_RESULTS_HEADERS = [
    "Date", "Topic", "Score", "Weak Questions",
    "Revision Needed", "Retest Date",
]

WEAK_AREAS_HEADERS = [
    "Topic", "Times Struggled", "Last Test Score",
    "Priority", "Extra Resources",
]

BOLD_FORMAT = {"textFormat": {"bold": True}}
