"""
Generates the A-to-Z setup guide PDF for AI Study Partner.
Run:    python docs/generate_setup_pdf.py
Output: docs/AI_Study_Partner_Setup_Guide.pdf
"""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Preformatted, Spacer, Table, TableStyle,
)

# ── Theme ──────────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#11122e")
BLUE   = colors.HexColor("#1e54b3")
TEAL   = colors.HexColor("#0a7074")
GREEN  = colors.HexColor("#1f8a4c")
AMBER  = colors.HexColor("#9a6a00")
LIGHT  = colors.HexColor("#f3f4f8")
CODEBG = colors.HexColor("#1b1d33")
GREY   = colors.HexColor("#5b5b6b")

OUT = os.path.join(os.path.dirname(__file__), "AI_Study_Partner_Setup_Guide.pdf")
CW = 16.4 * cm  # content width

# ── Styles ─────────────────────────────────────────────────────────────────────
S = {
    "cover_title": ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=32,
                                  textColor=colors.white, leading=38, alignment=TA_CENTER),
    "cover_sub":   ParagraphStyle("cs", fontName="Helvetica", fontSize=13,
                                  textColor=colors.HexColor("#c8cce8"), leading=20,
                                  alignment=TA_CENTER),
    "cover_meta":  ParagraphStyle("cmeta", fontName="Helvetica", fontSize=10,
                                  textColor=colors.HexColor("#9aa0c8"), leading=16,
                                  alignment=TA_CENTER),
    "h1":   ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=17,
                           textColor=NAVY, leading=22, spaceBefore=14, spaceAfter=6),
    "h2":   ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5,
                           textColor=BLUE, leading=17, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10.2,
                           textColor=colors.HexColor("#22232e"), leading=15, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=10.2,
                             textColor=colors.HexColor("#22232e"), leading=15,
                             leftIndent=15, bulletIndent=3, spaceAfter=3),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.8,
                           textColor=colors.white, leading=13),
    "tip":  ParagraphStyle("tip", fontName="Helvetica", fontSize=9.6,
                           textColor=colors.HexColor("#14361f"), leading=14),
    "warn": ParagraphStyle("warn", fontName="Helvetica", fontSize=9.6,
                           textColor=colors.HexColor("#5c3b00"), leading=14),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12.5,
                           textColor=colors.HexColor("#22232e")),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=9, leading=12.5,
                            textColor=colors.white),
}

story = []


# ── Helpers ────────────────────────────────────────────────────────────────────
def h1(txt):
    story.append(Paragraph(txt, S["h1"]))
    bar = Table([[""]], colWidths=[CW], rowHeights=[2.5])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)]))
    story.append(bar)
    story.append(Spacer(1, 6))


def h2(txt):
    story.append(Paragraph(txt, S["h2"]))


def body(txt):
    story.append(Paragraph(txt, S["body"]))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, S["bullet"], bulletText="•"))


def code(txt):
    inner = Preformatted(txt, S["code"])
    t = Table([[inner]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODEBG),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(Spacer(1, 2))
    story.append(t)
    story.append(Spacer(1, 6))


def callout(label, txt, bg, fg, style):
    inner = Paragraph(f"<b>{label}</b>&nbsp;&nbsp;{txt}", style)
    t = Table([[inner]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBEFORE", (0, 0), (0, -1), 3, fg),
    ]))
    story.append(t)
    story.append(Spacer(1, 7))


def tip(txt):
    callout("TIP", txt, colors.HexColor("#e3f5ea"), GREEN, S["tip"])


def warn(txt):
    callout("IMPORTANT", txt, colors.HexColor("#fbf0d9"), AMBER, S["warn"])


def step_banner(num, txt):
    cell = Paragraph(f'<font color="white"><b>STEP {num}</b></font>'
                     f'<font color="#c8cce8">&nbsp;&nbsp;&nbsp;{txt}</font>', S["body"])
    t = Table([[cell]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(Spacer(1, 10))
    story.append(t)
    story.append(Spacer(1, 7))


def table(headers, rows, col_widths):
    data = [[Paragraph(h, S["cellb"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), S["cell"]) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7d9e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))


# ════════════════════════════════════════════════════════════════════════════════
#  COVER
# ════════════════════════════════════════════════════════════════════════════════
story.append(Spacer(1, 4.5 * cm))
story.append(Paragraph("AI STUDY PARTNER", S["cover_title"]))
story.append(Spacer(1, 0.5 * cm))
story.append(Paragraph("Complete A&nbsp;to&nbsp;Z Setup Guide", S["cover_sub"]))
story.append(Spacer(1, 0.25 * cm))
story.append(Paragraph("Telegram Bot &bull; Gemini AI &bull; Google Sheets &bull; "
                       "Free 24/7 Hosting on Render", S["cover_sub"]))
story.append(Spacer(1, 2.0 * cm))
story.append(Paragraph("JMT Technologies&nbsp;&nbsp;|&nbsp;&nbsp;Sanjay V", S["cover_meta"]))
story.append(Paragraph("Workshop Edition&nbsp;&nbsp;|&nbsp;&nbsp;June 2026", S["cover_meta"]))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════════════════
#  OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
h1("What You Are Setting Up")
body("AI Study Partner is an autonomous study-mentor Telegram bot. A student just "
     "chats with it; the bot designs a study plan, tracks progress, runs quizzes, "
     "generates slides and research, and manages everything inside an auto-created "
     "Google Sheet. This guide takes you from zero to a live, always-on bot.")

h2("The big picture — 5 things to wire together")
bullets([
    "<b>Telegram</b> &ndash; the chat interface students use (bot token).",
    "<b>Gemini AI</b> &ndash; the brain that plans, quizzes and explains (API key).",
    "<b>Google Sheets</b> &ndash; the bot's memory / planner (service-account JSON).",
    "<b>Render</b> &ndash; free cloud host that runs the bot 24/7 (web service).",
    "<b>UptimeRobot</b> &ndash; free pinger that guarantees it never sleeps.",
])

tip("Total cost is <b>$0</b>. Every service here has a free tier that is more than "
    "enough for a workshop or a classroom.")

h2("Accounts you will need")
table(
    ["Account", "Used for", "Cost"],
    [
        ["Telegram", "Create the bot, get the token", "Free"],
        ["Google AI Studio", "Gemini API key", "Free"],
        ["Google Cloud", "Sheets + Drive service account", "Free"],
        ["GitHub", "Hold the code Render deploys from", "Free"],
        ["Render", "Host the bot 24/7", "Free"],
        ["UptimeRobot", "Keep it awake (recommended)", "Free"],
        ["Supabase", "Persistent database (optional)", "Free"],
    ],
    [3.5 * cm, 9.4 * cm, 3.5 * cm],
)

warn("Set aside about <b>30-40 minutes</b> the first time. Most of it is creating "
     "free accounts and copying keys. The bot needs no coding from you.")

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════════════════
#  PART 1 — KEYS & ACCOUNTS
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 1 &mdash; Get Your Keys &amp; Credentials")

step_banner(1, "Create the Telegram bot")
bullets([
    "Open Telegram, search for <b>@BotFather</b>, open the chat.",
    "Send the command <b>/newbot</b>.",
    "Choose a display name, e.g. <i>AI Study Partner</i>.",
    "Choose a username ending in <b>_bot</b>, e.g. <i>aistudypartner_bot</i>.",
    "BotFather replies with a <b>token</b> &ndash; copy it.",
])
code("TELEGRAM_BOT_TOKEN = 8123456789:AAH...your-long-token...xyz")
tip("Keep this token secret. Anyone who has it can control your bot.")

step_banner(2, "Get your free Gemini API key")
bullets([
    "Go to  https://aistudio.google.com/apikey",
    "Sign in with any Google account.",
    "Click <b>Create API Key</b>, then copy the key.",
])
code("GEMINI_API_KEY = AIzaSy...your-key...")

step_banner(3, "Create the Google Sheets service account")
body("This lets the bot create and edit Google Sheets on its own.")
bullets([
    "Go to  https://console.cloud.google.com  and create a new project "
    "(name it <i>AI Study Partner</i>).",
    "In the search bar, open <b>Google Sheets API</b> and click <b>Enable</b>.",
    "Search <b>Google Drive API</b> and click <b>Enable</b>.",
    "Open <b>APIs &amp; Services &gt; Credentials</b>.",
    "Click <b>Create Credentials &gt; Service Account</b>. Name it "
    "<i>study-partner-bot</i>, then Create and Done.",
    "Click the new service account, open the <b>Keys</b> tab, then "
    "<b>Add Key &gt; Create new key &gt; JSON</b>.",
    "A <b>credentials.json</b> file downloads. Keep it safe.",
])
warn("Inside credentials.json there is a field <b>client_email</b> (it looks like "
     "<i>...@...iam.gserviceaccount.com</i>). Copy it &ndash; that is your "
     "<b>SHEET_SHARE_EMAIL</b>.")
code("SHEET_SHARE_EMAIL = study-partner-bot@your-project.iam.gserviceaccount.com")

step_banner(4, "Convert credentials.json to one line (base64)")
body("Render stores secrets as text, so we encode the JSON file into a single "
     "base64 string for the <b>GOOGLE_CREDENTIALS_JSON</b> variable.")
h2("On Mac / Linux")
code("base64 -i credentials.json | tr -d '\\n'")
h2("On Windows (PowerShell)")
code('[Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))')
body("Copy the long output &ndash; that single line is your "
     "<b>GOOGLE_CREDENTIALS_JSON</b> value.")
tip("Running locally instead? You can skip base64 &ndash; just keep credentials.json "
    "in the project folder and set GOOGLE_CREDENTIALS_JSON=./credentials.json")

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════════════════
#  PART 2 — CODE
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 2 &mdash; Get the Code onto GitHub")
body("Render deploys from a GitHub repository. The project lives in the "
     "<b>ai_study_partner/</b> folder of your repo.")
bullets([
    "If the code is already in your GitHub repo, you are done with this part &ndash; "
    "skip to Part 3.",
    "To work on it locally first, clone it:",
])
code("git clone https://github.com/justmything04-lang/CHAT.git\n"
     "cd CHAT/ai_study_partner")
tip("The whole project is self-contained in the <b>ai_study_partner/</b> folder, so "
    "Render only needs that folder as its root directory.")

# ════════════════════════════════════════════════════════════════════════════════
#  PART 3 — RENDER
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 3 &mdash; Deploy to Render (Free Web Service)")

step_banner(5, "Create the web service")
bullets([
    "Go to  https://render.com  and sign in with GitHub.",
    "Click <b>New &gt; Web Service</b>.",
    "Select your repository (<i>CHAT</i>).",
])

step_banner(6, "Configure the service")
table(
    ["Setting", "Value"],
    [
        ["Root Directory", "ai_study_partner"],
        ["Language / Env", "Python 3"],
        ["Build Command", "pip install -r requirements.txt"],
        ["Start Command", "python main.py"],
        ["Instance Type", "Free"],
        ["Health Check Path", "/health"],
    ],
    [4.5 * cm, 11.9 * cm],
)
warn("The <b>Root Directory</b> must be <b>ai_study_partner</b>, otherwise Render "
     "will not find requirements.txt or main.py.")

step_banner(7, "Add the environment variables")
body("In the Render <b>Environment</b> tab, add these keys (values from Part 1):")
table(
    ["Variable", "Value / Note", "Required?"],
    [
        ["TELEGRAM_BOT_TOKEN", "from BotFather", "Yes"],
        ["GEMINI_API_KEY", "from AI Studio", "Yes"],
        ["GOOGLE_CREDENTIALS_JSON", "the base64 line", "Yes"],
        ["SHEET_SHARE_EMAIL", "service-account email", "Yes"],
        ["STORAGE_BACKEND", "sqlite (or supabase)", "Yes"],
        ["TIMEZONE", "Asia/Kolkata", "Yes"],
        ["KEEP_ALIVE_SECONDS", "600", "Yes"],
        ["RENDER_APP_URL", "added in Step 9", "Later"],
    ],
    [5.4 * cm, 7.6 * cm, 3.4 * cm],
)

step_banner(8, "Deploy and grab your URL")
bullets([
    "Click <b>Create Web Service</b>. Render installs and starts the bot.",
    "Wait for the log line <b>Bot starting in long-polling mode</b>.",
    "At the top of the page copy your service URL, e.g. "
    "https://ai-study-partner.onrender.com",
])

step_banner(9, "Turn on the 24/7 self-ping")
bullets([
    "Add one more environment variable:",
    "<b>RENDER_APP_URL</b> = the URL you just copied.",
    "Save. Render redeploys automatically.",
])
code("RENDER_APP_URL = https://ai-study-partner.onrender.com")
body("Now the bot pings itself every 10 minutes so the free instance never sleeps.")

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════════════════
#  PART 4 — 24/7
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 4 &mdash; Make It Truly Always-On")

step_banner(10, "Verify the health endpoint")
body("Open this URL in your browser:")
code("https://your-app.onrender.com/health")
body('You should see:   {"status": "ok", "service": "ai-study-partner"}')

step_banner(11, "Add an external monitor (recommended)")
body("The built-in self-ping keeps the bot awake while it is running, but it cannot "
     "wake a process that has already slept. A free external monitor closes that gap.")
bullets([
    "Go to  https://uptimerobot.com  and sign up free.",
    "Click <b>Add New Monitor &gt; HTTP(s)</b>.",
    "URL:  https://your-app.onrender.com/health",
    "Monitoring interval: <b>5 minutes</b>, then Create.",
])
tip("Self-ping plus UptimeRobot together give genuine round-the-clock uptime on "
    "Render's free plan.")

warn("With <b>STORAGE_BACKEND=sqlite</b>, student data resets whenever Render "
     "redeploys (its disk is temporary). For a one-day workshop that is fine. To keep "
     "data permanently, use <b>STORAGE_BACKEND=supabase</b> (see Part 6).")

# ════════════════════════════════════════════════════════════════════════════════
#  PART 5 — USE IT
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 5 &mdash; Test &amp; Use the Bot")
step_banner(12, "Talk to your bot")
bullets([
    "Open Telegram and search your bot's <b>@username</b>.",
    "Send <b>/start</b>. It should ask for your name.",
    "Give a goal like <i>CA Inter GST in 20 days</i> and a target date.",
    "It builds a plan and shares a Google Sheet link. You are live!",
])

h2("Command cheat-sheet")
table(
    ["Command", "What it does"],
    [
        ["/start", "Onboard and create the study plan + sheet"],
        ["/today", "Today's study targets"],
        ["/done [topic]", "Mark a topic complete"],
        ["/test [topic]", "5-question MCQ quiz"],
        ["/stuck [topic]", "Flag a weak area"],
        ["/progress", "Progress report + dashboard snapshot"],
        ["/reschedule", "Reshuffle the remaining plan"],
        ["/research [topic]", "Deep research summary"],
        ["/explain [topic]", "Plain-language explanation"],
        ["/slides [topic]", "Generate a Gamma slide-deck link"],
        ["/upload [subject]", "Upload a PDF (NotebookLM)"],
        ["/ask [question]", "Ask from your uploaded PDF"],
        ["/settings", "Change briefing time and alert frequency"],
        ["/help", "List every command"],
    ],
    [4.6 * cm, 11.8 * cm],
)
tip("Students can also just chat normally &ndash; \"I finished chapter 3\" works the "
    "same as /done.")

story.append(PageBreak())

# ════════════════════════════════════════════════════════════════════════════════
#  PART 6 — OPTIONAL
# ════════════════════════════════════════════════════════════════════════════════
h1("Part 6 &mdash; Optional Upgrades")

h2("A. Persistent database with Supabase")
bullets([
    "Create a free project at  https://supabase.com",
    "Open <b>SQL Editor</b>, paste the contents of <b>supabase_setup.sql</b>, Run.",
    "From <b>Project Settings &gt; API</b>, copy the URL and the key.",
    "On Render set: STORAGE_BACKEND=supabase, SUPABASE_URL=..., SUPABASE_KEY=...",
])

h2("B. Slides with Gamma (no API key)")
bullets([
    "Create a free account at  https://gamma.app",
    "Stay logged in there in your browser.",
    "When a student uses /slides, the bot sends a one-click link that opens a "
    "pre-filled deck &ndash; they just hit Generate.",
])

h2("C. Study from your own PDFs (NotebookLM)")
body("Optional and unofficial. If installed, /upload, /ask and /podcast use "
     "NotebookLM; if not, the bot automatically falls back to Gemini.")
code("pip install git+https://github.com/teng-lin/notebooklm-py.git")

# ════════════════════════════════════════════════════════════════════════════════
#  TROUBLESHOOTING
# ════════════════════════════════════════════════════════════════════════════════
h1("Troubleshooting")
table(
    ["Symptom", "Fix"],
    [
        ["Bot does not reply at all",
         "Check Render logs. Confirm TELEGRAM_BOT_TOKEN is correct."],
        ["409 Conflict in logs",
         "Another instance/webhook is active. Redeploy; the bot auto-clears webhooks."],
        ["Sheet not created / permission error",
         "Enable Sheets API + Drive API; recheck GOOGLE_CREDENTIALS_JSON base64."],
        ["Gemini errors / empty replies",
         "Verify GEMINI_API_KEY and that you have free quota left."],
        ["Bot sleeps after 15 minutes",
         "Set RENDER_APP_URL and add the UptimeRobot monitor."],
        ["Data lost after a redeploy",
         "Expected on sqlite. Switch STORAGE_BACKEND to supabase."],
        ["Briefings not arriving",
         "Service must stay awake (Part 4). Check TIMEZONE is correct."],
    ],
    [5.4 * cm, 11.0 * cm],
)

h1("Environment Variables &mdash; Full Reference")
table(
    ["Variable", "Required", "Example / Default"],
    [
        ["TELEGRAM_BOT_TOKEN", "Yes", "8123...:AAH..."],
        ["GEMINI_API_KEY", "Yes", "AIzaSy..."],
        ["GOOGLE_CREDENTIALS_JSON", "Yes", "base64 string"],
        ["SHEET_SHARE_EMAIL", "Yes", "...@...iam.gserviceaccount.com"],
        ["STORAGE_BACKEND", "Yes", "sqlite | supabase | gsheet"],
        ["TIMEZONE", "Yes", "Asia/Kolkata"],
        ["RENDER_APP_URL", "Yes (host)", "https://app.onrender.com"],
        ["KEEP_ALIVE_SECONDS", "No", "600"],
        ["SUPABASE_URL", "If supabase", "https://xxx.supabase.co"],
        ["SUPABASE_KEY", "If supabase", "eyJ..."],
        ["GAMMA_BASE_URL", "No", "https://gamma.app/create"],
        ["GAMMA_DEFAULT_CARDS", "No", "10"],
    ],
    [5.6 * cm, 3.2 * cm, 7.6 * cm],
)

story.append(Spacer(1, 6))
story.append(Paragraph(
    "You now have a fully autonomous, always-on AI Study Partner. Happy teaching!",
    ParagraphStyle("end", fontName="Helvetica-Bold", fontSize=11,
                   textColor=TEAL, alignment=TA_CENTER, spaceBefore=10)))


# ── Page furniture ──────────────────────────────────────────────────────────────
def cover_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(TEAL)
    canvas.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, stroke=0, fill=1)
    canvas.rect(0, 0, A4[0], 6 * mm, stroke=0, fill=1)
    canvas.restoreState()


def content_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.1 * cm, "AI Study Partner  |  Setup Guide")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page - 1}")
    canvas.setStrokeColor(colors.HexColor("#dcdde8"))
    canvas.line(2 * cm, 1.45 * cm, A4[0] - 2 * cm, 1.45 * cm)
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm)
cover_frame = Frame(0, 0, A4[0], A4[1], id="cover",
                    leftPadding=2 * cm, rightPadding=2 * cm)
content_frame = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm, id="content")
doc.addPageTemplates([
    PageTemplate(id="Cover", frames=[cover_frame], onPage=cover_bg),
    PageTemplate(id="Content", frames=[content_frame], onPage=content_footer),
])
story.insert(0, NextPageTemplate("Content"))

doc.build(story)
print(f"PDF written: {OUT}")
print(f"size: {os.path.getsize(OUT) // 1024} KB")
