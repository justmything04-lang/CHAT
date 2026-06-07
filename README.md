# 🤖 AI Study Partner

> **Autonomous AI personal mentor on Telegram.**  
> Student just chats. AI plans, tracks, tests, adapts — and manages everything in a Google Sheet.

Built by **Sanjay V — JMT Technologies** · Workshop June 7, 2026

---

## What It Does

| Student Types | AI Does Automatically |
|---|---|
| "I want to crack CA Inter GST in 20 days" | Creates full study plan, Google Sheet (7 tabs), sends sheet link |
| "I finished Chapter 3, struggled with ITC" | Marks done, flags ITC as weak area, reschedules revision, updates dashboard |
| "Give me today's targets" | Reads sheet → sends topics, hours, difficulty |
| "Test me on Chapter 3" | Generates 5 MCQs, conducts quiz, scores, updates Test Results tab |
| "Make slides for Input Tax Credit" | Generates outline via Gemini → sends direct Gamma link (1 click to deck) |
| "I'm confused about RCM" | Deep research Sparkpage-style summary sent on Telegram |
| "I'm 3 days behind" | Reshuffles entire remaining plan intelligently |
| *(no message for 2 days)* | Sends automatic follow-up with recovery plan |

**The student NEVER touches the Google Sheet. Ever.**

---

## Tech Stack

| Component | Technology |
|---|---|
| Bot | python-telegram-bot 20.7 (async) |
| AI Brain | Gemini 2.0 Flash (free API) |
| Study Planner | Google Sheets API · gspread 6 |
| Slides | Gamma deep-link (no API key) |
| Material Q&A | notebooklm-py + Gemini fallback |
| Session DB | SQLite (default) · Supabase · GSheet |
| Scheduler | APScheduler via PTB job-queue |
| Hosting | Render / Railway (free tier) |
| Language | Python 3.10+ |

**Total cost: $0**

---

## Bot Commands

### Study Management
| Command | What it does |
|---|---|
| `/start` | Onboarding — collect name, goal, date → create plan + sheet |
| `/today` | Today's study targets from the sheet |
| `/done [topic]` | Mark topic complete, update progress |
| `/stuck [topic]` | Flag weak area, add to tracker |
| `/progress` | Full progress report + dashboard snapshot |
| `/reschedule` | AI reshuffles remaining plan |
| `/report` | Weekly summary |

### AI Tools
| Command | What it does |
|---|---|
| `/test [topic]` | 5-question MCQ quiz, auto-scored |
| `/research [topic]` | Sparkpage-style structured summary |
| `/explain [topic]` | Plain-language explanation (≤150 words) |
| `/compare [A] vs [B]` | Side-by-side concept comparison |
| `/mnemonic [topic]` | Memory trick / acronym |
| `/slides [topic]` | Gemini outline → Gamma deep link (1-click slide deck) |

### Your Material
| Command | What it does |
|---|---|
| `/upload [subject]` | Upload PDF → NotebookLM notebook (Gemini fallback) |
| `/ask [question]` | Ask from your uploaded study material |
| `/podcast [subject]` | Audio overview of notes → MP3 on Telegram |

### Settings
| Command | What it does |
|---|---|
| `/settings` | Inline keyboard: change briefing time, alert frequency, reset |

**Natural language works too** — "I finished chapter 3" is the same as `/done Chapter 3`.

---

## Google Sheet — 7 Tabs

| Tab | Purpose | Who touches it |
|---|---|---|
| **1 DASHBOARD** | Visual cards: progress%, streak, status, this week, weak areas, resources | Bot rebuilds automatically |
| **2 STUDY_PLAN** | Day-by-day plan with status colour-coding | Bot writes, user reads |
| **3 PROGRESS_LOG** | Every update the student reports | Bot writes |
| **4 TEST_RESULTS** | Quiz scores, weak questions, retest dates | Bot writes |
| **5 WEAK_AREAS** | Topics struggled with, priority, extra resources | Bot writes |
| **6 RESOURCES** | Gamma slide links, NotebookLM links, research saved | Bot writes |
| **7 SESSION** | Meta / session data (used by GSheet storage backend) | Bot only |

### Dashboard Snapshot
When `/progress` is called, the bot exports Tab 1 as a PNG via Google's own export API and sends it directly on Telegram — no extra tools needed.

---

## Project Structure

```
ai_study_partner/
├── main.py                        ← entry point, webhook/polling toggle
├── .env.example                   ← all env vars with instructions
├── requirements.txt
├── render.yaml
├── supabase_setup.sql             ← run in Supabase SQL editor for that backend
│
├── bot/
│   ├── handlers.py                ← core commands + onboarding state machine
│   ├── nlp_router.py              ← 2-pass intent: keywords → Gemini fallback
│   ├── settings_ui.py             ← /settings inline keyboard
│   ├── slides_handler.py          ← /slides + Gamma onboarding callbacks
│   ├── research_handlers.py       ← /research /explain /compare /mnemonic
│   └── notebooklm_handlers.py     ← /upload /ask /podcast
│
├── ai/
│   └── gemini_client.py           ← all Gemini API calls
│
├── sheets/
│   ├── sheets_manager.py          ← create/read/write all 7 tabs
│   ├── dashboard_builder.py       ← rebuilds visual Tab 1 with colours
│   ├── snapshot.py                ← exports Tab 1 as PNG → sends to Telegram
│   └── sheet_templates.py         ← tab names, headers, colour constants
│
├── tools/
│   ├── gamma_links.py             ← Gamma deep-link URL builder
│   └── notebooklm_client.py       ← NotebookLM wrapper + Gemini fallback
│
├── scheduler/
│   └── daily_jobs.py              ← per-user briefing + inactivity jobs
│
├── storage/
│   ├── base.py                    ← abstract storage interface
│   ├── factory.py                 ← returns correct backend via STORAGE_BACKEND
│   ├── sqlite_store.py            ← default, zero-config
│   ├── supabase_store.py          ← production-ready, free 500 MB
│   └── gsheet_store.py            ← Google Sheet as flat DB
│
├── state/
│   └── session.py                 ← thin wrapper over storage backend
│
└── data/                          ← SQLite DB + session files
```

---

## Quick Setup (Local)

### Step 1 — Clone & install
```bash
git clone https://github.com/justmything04-lang/CHAT.git
cd CHAT/ai_study_partner
pip install -r requirements.txt
```

### Step 2 — Telegram bot
1. Open Telegram → search `@BotFather` → `/newbot`
2. Give it a name and username (must end in `_bot`)
3. Copy the token

### Step 3 — Gemini API key
1. Go to https://aistudio.google.com/apikey
2. Sign in → Create API Key → copy

### Step 4 — Google Sheets API
1. Go to https://console.cloud.google.com
2. Create project → Enable **Google Sheets API** + **Google Drive API**
3. Go to Credentials → Create Service Account → create key → download `credentials.json`
4. Copy the service account email from the JSON file

### Step 5 — Create .env
```bash
cp .env.example .env
# Fill in: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, GOOGLE_CREDENTIALS_JSON, SHEET_SHARE_EMAIL
```

For `GOOGLE_CREDENTIALS_JSON`, base64-encode your credentials file:
```bash
# Linux/Mac:
base64 -i credentials.json | tr -d '\n'
# Paste the output into .env
```

Or for local dev, just set it to the path:
```bash
GOOGLE_CREDENTIALS_JSON=./credentials.json  # and keep the file locally
```
> For local dev only: if `credentials.json` already exists in the project folder, `main.py` uses it directly without decoding from the env var.

### Step 6 — Run
```bash
python main.py
# → starts in polling mode
# → open Telegram, message your bot /start
```

---

## Deploy to Render (Free Tier)

1. Push code to GitHub
2. Go to https://render.com → **New → Web Service**
3. Connect your GitHub repo, set root directory to `ai_study_partner`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`
6. Add all env vars from `.env.example` in the Render **Environment** tab
7. Set `RENDER_APP_URL` = your Render service URL (e.g. `https://ai-study-partner.onrender.com`)
8. Set `STORAGE_BACKEND=supabase` + Supabase credentials for persistent storage

> **Important:** Render free tier has an ephemeral filesystem. With `STORAGE_BACKEND=sqlite`, data resets on every redeploy. Use `supabase` for production.

---

## Storage Backends

| Backend | Setup | Best for |
|---|---|---|
| `sqlite` | Zero config, auto-created | Local dev, workshops |
| `supabase` | Free project + run `supabase_setup.sql` | Production on Render |
| `gsheet` | Set `GSHEET_DB_ID` | Educational / demos |

---

## User-Configurable via Telegram

Users change settings in-chat — no config files needed:

- **Briefing time** → `/settings` → 🕐 Briefing → type new time (HH:MM)
- **Inactivity alerts** → `/settings` → 🔔 Alert → choose: Hourly / Daily / Every 2 Days / Weekly / Never
- **Reset all data** → `/settings` → 🗑️ Reset (with confirmation)

---

## Gamma Slides (Free, No API Key)

1. User types `/slides GST Chapter 3`
2. Bot generates 10-slide outline via Gemini
3. Bot URL-encodes content → `https://gamma.app/create?text=...&cards=10`
4. Bot sends an inline button: **🚀 OPEN IN GAMMA →**
5. User clicks (while logged into Gamma) → lands on pre-filled editor → hit Generate → done in 10 seconds

First time: one-time Gamma setup flow (bot checks if user has an account + is logged in).

---

## Contributing

This project is open source under the MIT License.  
Pull requests welcome — especially for new AI features and storage backends.

---

## License

MIT © 2026 Sanjay V — JMT Technologies
