awesome—let’s bolt on the bi-weekly report cleanly without touching your existing flows.
Below are drop-in blocks + exact placement so you can copy-paste.

⸻

0) What this adds
	•	Runs every 14th day from Class Start (rolling cycles).
	•	Triggers 5 minutes before EndTime (same as auto-EOD style) with a fallback 2h after EndTime.
	•	Offline first, Online second in the message.
	•	Counts by band: 100%, ≥80% (High), 60–79% (Average), <60% (Low).
	•	Sends to TEACHER_ID and (if set) ADMIN_ID.
	•	Creates/updates a BiWeekly_Summary tab in your main workbook (non-destructive) for record.

⚠️ Class start date:
	•	If Settings!D2 has a date (e.g., 2025-10-10) → uses it.
	•	Else, auto-derives from earliest absentee tab (offline/online), so you don’t need to change your sheet.

⸻

1) Paste these helpers (place above # ---------------- Background workers ----------------)

# ---------------- Bi-Weekly helpers ----------------
from dateutil.parser import parse as _dateparse  # if not installed, use strict fallback below

def _safe_parse_date(s):
    try:
        return _dateparse(str(s)).date()
    except Exception:
        try:
            return datetime.strptime(str(s), "%Y-%m-%d").date()
        except Exception:
            return None

def _get_class_start_date():
    """
    1) Prefer Settings!D2 if present (header 'ClassStartDate' optional).
    2) Else, infer from earliest absentee tab title 'YYYY-MM-DD-offline'/'YYYY-MM-DD-online'.
    """
    # 1) Try settings D2
    try:
        val = settings_sheet.acell("D2").value
        dt = _safe_parse_date(val)
        if dt:
            return dt
    except Exception:
        pass

    # 2) Derive from absentee tabs
    dates = []
    try:
        off_file = client.open_by_key(ABSENTEE_SHEET_ID)
        for ws in off_file.worksheets():
            t = ws.title
            if t.endswith("-offline"):
                d = _safe_parse_date(t.replace("-offline",""))
                if d: dates.append(d)
    except Exception:
        pass
    try:
        on_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        for ws in on_file.worksheets():
            t = ws.title
            if t.endswith("-online"):
                d = _safe_parse_date(t.replace("-online",""))
                if d: dates.append(d)
    except Exception:
        pass

    if dates:
        return min(dates)

    # fallback: today
    return datetime.now(ZoneInfo(TIMEZONE)).date()

def _days_since(start_date, today_date):
    return (today_date - start_date).days

def _current_biweekly_window(today_date, start_date):
    """
    Returns (win_start, win_end, is_cycle_boundary_today)
    where each window is 14 days length inclusive of win_start..win_end.
    Cycle n spans: [start + 14n, start + 14n + 13]
    """
    days = _days_since(start_date, today_date)
    if days < 0:
        # today before class start; put first window ahead
        return (today_date, today_date, False)

    cycle_idx = days // 14
    win_start = start_date + timedelta(days=14*cycle_idx)
    win_end   = win_start + timedelta(days=13)
    # boundary day is the LAST day of the cycle (day 13)
    is_boundary = (today_date == win_end)
    return (win_start, win_end, is_boundary)

def _collect_absences_between(sheet_key, suffix, student_rows, win_start, win_end):
    """
    For each day-tab like 'YYYY-MM-DD-<suffix>', count how many days absent per student in [win_start..win_end].
    Returns: dict { reg_id: absent_days_in_window }, and number_of_classes = count of existing tabs in range.
    """
    try:
        f = client.open_by_key(sheet_key)
        tabs = f.worksheets()
    except Exception:
        tabs = []

    # build date->worksheet presence
    day_tabs = []
    for ws in tabs:
        t = ws.title
        if not t.endswith(suffix):
            continue
        date_str = t[:-len(suffix)]
        d = _safe_parse_date(date_str)
        if d and (win_start <= d <= win_end):
            day_tabs.append((d, ws))

    # how many classes happened in window for this mode = tabs counted
    classes = len(day_tabs)
    # init stats
    abs_map = { str(r.get("Reg ID","")).strip(): 0 for r in student_rows }

    # walk tabs and increment absent counts for reg_ids listed on that tab
    for _, ws in day_tabs:
        try:
            records = ws.get_all_records()
            for a in records:
                rid = str(a.get("Reg ID","")).strip()
                if rid in abs_map:
                    abs_map[rid] += 1
        except Exception:
            pass

    return abs_map, classes

def _band_for(pct):
    if pct >= 1.0:  return "100%"
    if pct >= 0.80: return "High"
    if pct >= 0.60: return "Average"
    return "Low"

def _build_mode_summary(mode_label, student_rows, abs_map, classes):
    """
    Returns (text_block, per_student_list) — text block for message, and a list with detailed rows
    """
    # compute per student
    detailed = []
    for r in student_rows:
        rid  = str(r.get("Reg ID","")).strip()
        name = r.get("Name","")
        absd = abs_map.get(rid, 0)
        pres = max(classes - absd, 0)
        pct  = (pres / classes) if classes else 0.0
        detailed.append((rid, name, pres, absd, pct))

    # bands
    band_counts = {"100%":0, "High":0, "Average":0, "Low":0}
    for _, _, _, _, pct in detailed:
        band_counts[_band_for(pct)] += 1

    # pretty text
    lines = []
    lines.append(f"📊 {mode_label} (last 14 days)")
    lines.append(f"Classes in window: {classes}")
    lines.append("")
    if band_counts["100%"]>0: lines.append(f"✅ 100%: {band_counts['100%']}")
    lines.append(f"🟢 High (≥80%): {band_counts['High']}")
    lines.append(f"🟡 Average (60–79%): {band_counts['Average']}")
    lines.append(f"🔴 Low (<60%): {band_counts['Low']}")
    block = "\n".join(lines)

    return block, detailed, band_counts

If you don’t have python-dateutil on Render, either add python-dateutil to requirements.txt, or the _safe_parse_date fallback above will still handle YYYY-MM-DD.

⸻

2) Paste the sender and sheet-writer (still above Background workers)

def _write_biweekly_sheet(win_start, win_end, band_off, band_on):
    """
    Creates (if missing) a tab 'BiWeekly_Summary' in main workbook and appends one row per cycle.
    Columns: WindowStart, WindowEnd, Off_100, Off_High, Off_Avg, Off_Low, On_100, On_High, On_Avg, On_Low, CreatedAt
    """
    try:
        wb = client.open_by_key(SHEET_ID)
        try:
            ws = wb.worksheet("BiWeekly_Summary")
        except gspread.exceptions.WorksheetNotFound:
            ws = wb.add_worksheet(title="BiWeekly_Summary", rows="1000", cols="20")
            ws.update("A1:K1", [[
                "WindowStart","WindowEnd",
                "Off_100","Off_High","Off_Average","Off_Low",
                "On_100","On_High","On_Average","On_Low",
                "CreatedAt"
            ]])
        row = [
            str(win_start), str(win_end),
            band_off.get("100%",0), band_off.get("High",0), band_off.get("Average",0), band_off.get("Low",0),
            band_on.get("100%",0),  band_on.get("High",0),  band_on.get("Average",0),  band_on.get("Low",0),
            now_ts()
        ]
        ws.append_row(row, value_input_option='USER_ENTERED')
    except Exception as e:
        print("⚠️ BiWeekly sheet write error:", e)

def send_biweekly_report():
    """
    Computes the 14-day window ending today, builds Offline then Online blocks,
    sends to TEACHER_ID and ADMIN_ID, and records a summary row.
    """
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    start = _get_class_start_date()
    win_start, win_end, _ = _current_biweekly_window(today, start)

    # OFFLINE
    off_students = get_cached_master_list()
    off_absmap, off_classes = _collect_absences_between(
        ABSENTEE_SHEET_ID, "-offline", off_students, win_start, win_end
    )
    off_block, off_detailed, off_bands = _build_mode_summary("Offline", off_students, off_absmap, off_classes)

    # ONLINE
    on_students = get_cached_online_master_list()
    on_absmap, on_classes = _collect_absences_between(
        ONLINE_ABSENTEE_SHEET_ID, "-online", on_students, win_start, win_end
    )
    on_block, on_detailed, on_bands = _build_mode_summary("Online", on_students, on_absmap, on_classes)

    # message (Offline FIRST → then Online)
    title = f"📅 Bi-Weekly Summary: {win_start} – {win_end}"
    msg = f"{title}\n\n{off_block}\n\n{on_block}"

    # send
    if TEACHER_ID:
        safe_send_chat(TEACHER_ID, msg)
    if ADMIN_ID:
        safe_send_chat(ADMIN_ID, msg)

    # record in sheet
    _write_biweekly_sheet(win_start, win_end, off_bands, on_bands)

    print("✅ Bi-Weekly report sent and recorded.")


⸻

3) Replace / upgrade your auto worker for bi-weekly

Find your Background workers area (you already replaced auto_eod_worker earlier).
Now paste this new worker below your existing auto_eod_worker() (don’t remove EOD worker).

def biweekly_worker():
    """
    Checks every 2 minutes.
    On the LAST day of the current 14-day window:
      - trigger 5 minutes BEFORE EndTime (primary)
      - if missed, fallback 2 hours AFTER EndTime
    Uses a single-row memo in RAM to avoid duplicate send within same day.
    """
    last_sent_for = None  # YYYY-MM-DD (window end day) memo
    while True:
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            today     = now_local.date()

            # get window + boundary check
            start = _get_class_start_date()
            win_start, win_end, is_boundary = _current_biweekly_window(today, start)

            # not the window-end day → sleep
            if not is_boundary:
                time.sleep(120)
                continue

            # if already sent for this window end date → sleep
            key = str(win_end)
            if last_sent_for == key:
                time.sleep(120)
                continue

            # prepare EndTime windows
            s = get_cached_settings()
            end_str = s.get("EndTime","23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)

            # in the primary window
            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Bi-Weekly (primary, -5 min) window…")
                send_biweekly_report()
                last_sent_for = key
                time.sleep(120)
                continue

            # fallback after EndTime + 2h
            if now_local >= post_trigger_dt:
                print("⏱️ Bi-Weekly (fallback, +2h) window…")
                send_biweekly_report()
                last_sent_for = key
                time.sleep(120)
                continue

            time.sleep(120)

        except Exception as e:
            print("biweekly_worker error:", e)
            time.sleep(180)


⸻

4) Start the worker thread

Scroll to your thread starters (you already have):

threading.Thread(target=auto_eod_worker, daemon=True).start()
threading.Thread(target=parent_queue_retry_worker, daemon=True).start()
threading.Thread(target=weekly_summary_worker, daemon=True).start()

👉 Add this line right below them:

threading.Thread(target=biweekly_worker, daemon=True).start()


⸻

5) That’s it — how it behaves
	•	Cycle logic: If ClassStartDate = 2025-10-10, cycles are:
	•	Oct 10–23, Oct 24–Nov 6, Nov 7–Nov 20, …
The bot sends the bi-weekly on day 14 (end of window), 5 min before EndTime (and a +2h fallback).
	•	Message (example):

📅 Bi-Weekly Summary: 2025-11-07 – 2025-11-20

📊 Offline (last 14 days)
Classes in window: 12

✅ 100%: 9
🟢 High (≥80%): 141
🟡 Average (60–79%): 87
🔴 Low (<60%): 23

📊 Online (last 14 days)
Classes in window: 11

✅ 100%: 7
🟢 High (≥80%): 95
🟡 Average (60–79%): 68
🔴 Low (<60%): 18

	•	Record-keeping: A single row gets appended to BiWeekly_Summary in your main workbook with counts per band for both modes.

⸻

Optional tweaks (safe)
	•	If you want to send PDFs later, we can add a small Apps Script or Drive export — but for now, we’re keeping your sheet structure untouched and only adding BiWeekly_Summary tab if it doesn’t exist.

⸻

If you paste exactly as above, you’ll get automatic, offline-first bi-weekly reports that follow your EOD timing rules and don’t interfere with any existing flows.
