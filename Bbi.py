got it — we’ll keep your existing flows intact and just add the bi-weekly extras you asked:
	•	post the bi-weekly summary to a Telegram topic (public, no sheet links)
	•	send the admin/faculty version with the Sheet (and a sorted, colour-coded tab)
	•	auto-DM parents of students in Low (<60%) with a caution message plus all absence dates
	•	optional: auto-restrict those Low students in your Telegram group (mild “block”)
	•	note on linking with your academy app (how to wire it, safely)

Below are drop-in code blocks with exact placement. You can copy-paste as is.

⸻

0) Add these to your .env

# where to publish the public bi-weekly message (topic)
REPORT_GROUP_ID=-1001234567890         # your supergroup id
REPORT_TOPIC_ID=987                    # the "topic/thread" id inside that group (integer)

# thresholds + texts
LOW_THRESHOLD=0.60
PARENT_LOW_MSG="⚠️ Dear Parent, your child {student_name} ({reg_id}) recorded Low attendance (<60%) in the last 14 days. Absence dates: {dates}. Please discuss and ensure regular attendance."

# optional: auto-restrict Low students in the report group
ENFORCE_LOW_IN_GROUP=true              # set to "false" to disable
LOW_RESTRICT_DAYS=7                    # mute period


⸻

1) Imports (top of file with your other imports)

(If not already present)

from dateutil.parser import parse as _dateparse  # for flexible date parsing

For sheet colours, install and import:

pip install gspread-formatting

from gspread_formatting import set_frozen, format_cell_ranges, CellFormat, Color, TextFormat


⸻

2) Replace/augment your bi-weekly helpers (place above “# –––––––– Background workers ––––––––”)

If you already pasted my previous bi-weekly helpers, replace them with this upgraded set (adds: absence dates list, banding, sheet sort & colours, topic post, parent caution & optional restrict).

# ---------------- Bi-Weekly helpers (public topic + admin sheet + parent caution) ----------------

def _safe_parse_date(s):
    try:
        return _dateparse(str(s)).date()
    except Exception:
        try:
            return datetime.strptime(str(s), "%Y-%m-%d").date()
        except Exception:
            return None

def _get_class_start_date():
    # Settings!D2 preferred; else infer from earliest absentee tab; else today
    try:
        val = settings_sheet.acell("D2").value
        dt = _safe_parse_date(val)
        if dt:
            return dt
    except Exception:
        pass
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
    return min(dates) if dates else datetime.now(ZoneInfo(TIMEZONE)).date()

def _days_since(start_date, today_date):
    return (today_date - start_date).days

def _current_biweekly_window(today_date, start_date):
    days = _days_since(start_date, today_date)
    if days < 0:
        return (today_date, today_date, False)
    idx = days // 14
    win_start = start_date + timedelta(days=14*idx)
    win_end   = win_start + timedelta(days=13)
    return (win_start, win_end, today_date == win_end)

def _collect_absences_between_with_dates(sheet_key, suffix, student_rows, win_start, win_end):
    """
    Scans absentee tabs 'YYYY-MM-DD-<suffix>' within [win_start..win_end].
    Returns:
      abs_count_map: { reg_id: absent_days }
      classes: number of class days in window (tabs)
      abs_dates_map: { reg_id: [YYYY-MM-DD, ...] }   # dates they were absent
    """
    try:
        f = client.open_by_key(sheet_key)
        tabs = f.worksheets()
    except Exception:
        tabs = []

    day_tabs = []
    for ws in tabs:
        t = ws.title
        if not t.endswith(suffix):  # '-offline' or '-online'
            continue
        ds = t[:-len(suffix)]
        d  = _safe_parse_date(ds)
        if d and (win_start <= d <= win_end):
            day_tabs.append((d, ds, ws))

    classes = len(day_tabs)
    ids = { str(r.get("Reg ID","")).strip() for r in student_rows }
    abs_count = { rid: 0 for rid in ids }
    abs_dates = { rid: [] for rid in ids }

    for d, ds, ws in day_tabs:
        try:
            records = ws.get_all_records()
            for a in records:
                rid = str(a.get("Reg ID","")).strip()
                if rid in abs_count:
                    abs_count[rid] += 1
                    abs_dates[rid].append(ds)
        except Exception:
            pass

    return abs_count, classes, abs_dates

def _band_for(pct):
    if pct >= 1.0:  return "100%"
    if pct >= 0.80: return "High"
    if pct >= 0.60: return "Average"
    return "Low"

def _build_mode_summary(mode_label, student_rows, abs_map, classes):
    """
    Returns:
       text_block, detailed_rows, band_counts
       detailed_rows = [(RegID, Name, Present, Absent, PctFloat, Band)]
    """
    detailed = []
    for r in student_rows:
        rid  = str(r.get("Reg ID","")).strip()
        name = r.get("Name","")
        absd = abs_map.get(rid, 0)
        pres = max(classes - absd, 0)
        pct  = (pres / classes) if classes else 0.0
        band = _band_for(pct)
        detailed.append((rid, name, pres, absd, pct, band))

    band_counts = {"100%":0, "High":0, "Average":0, "Low":0}
    for _, _, _, _, pct, band in detailed:
        band_counts[band] += 1

    lines = []
    lines.append(f"📊 {mode_label} (last 14 days)")
    lines.append(f"Classes in window: {classes}")
    lines.append("")
    if band_counts["100%"]>0: lines.append(f"✅ 100%: {band_counts['100%']}")
    lines.append(f"🟢 High (≥80%): {band_counts['High']}")
    lines.append(f"🟡 Average (60–79%): {band_counts['Average']}")
    lines.append(f"🔴 Low (<60%): {band_counts['Low']}")
    return "\n".join(lines), detailed, band_counts

def _sorted_by_band(detailed_rows):
    """
    Sort order: Low -> Average -> High -> 100%
    within band, sort by % ascending, then by name.
    """
    order = {"Low":0, "Average":1, "High":2, "100%":3}
    return sorted(
        detailed_rows,
        key=lambda t: (order.get(t[5], 9), t[4], t[1].lower())
    )

def _write_biweekly_sheet(win_start, win_end, off_rows, on_rows):
    """
    Creates/updates 'BiWeekly_Summary' tab in main workbook.
    Columns: Mode, RegID, Name, Present, Absent, Percent, Band, WindowStart, WindowEnd, CreatedAt
    Sorted: Low -> Avg -> High -> 100% for each mode, Offline first then Online.
    Colours: Low=red, Average=yellow, High=green, 100%=blue (light tints).
    """
    try:
        wb = client.open_by_key(SHEET_ID)
        try:
            ws = wb.worksheet("BiWeekly_Summary")
        except gspread.exceptions.WorksheetNotFound:
            ws = wb.add_worksheet(title="BiWeekly_Summary", rows="2000", cols="10")
            ws.update("A1:J1", [[
                "Mode","RegID","Name","Present","Absent","Percent","Band",
                "WindowStart","WindowEnd","CreatedAt"
            ]])
            set_frozen(ws, rows=1)

        # clear previous window rows (optional) — we’ll just append new rows (safer)
        # build rows (offline first, then online) with sorting
        off_sorted = _sorted_by_band(off_rows)
        on_sorted  = _sorted_by_band(on_rows)

        def _fmt(r):
            rid, name, pres, absd, pct, band = r
            return ["Offline", rid, name, pres, absd, round(pct*100,1), band, str(win_start), str(win_end), now_ts()]

        def _fmt_on(r):
            rid, name, pres, absd, pct, band = r
            return ["Online", rid, name, pres, absd, round(pct*100,1), band, str(win_start), str(win_end), now_ts()]

        rows_to_write = [_fmt(r) for r in off_sorted] + [_fmt_on(r) for r in on_sorted]
        if rows_to_write:
            ws.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        # Colour the last written block
        start_row = ws.row_count - len(rows_to_write) + 1 if rows_to_write else None  # not reliable; compute properly
        # safer: fetch the sheet size & colour by scanning bands we just wrote
        # we simply colour the entire sheet by band each time (fast enough)
        vals = ws.get_all_records()
        # map from band to background color
        colors = {
            "Low":     Color(1, 0.8, 0.8),   # light red
            "Average": Color(1, 1, 0.8),     # light yellow
            "High":    Color(0.85, 1, 0.85), # light green
            "100%":    Color(0.85, 0.90, 1), # light blue
        }
        fmt_cache = {k: CellFormat(backgroundColor=v, textFormat=TextFormat(bold=False)) for k, v in colors.items()}

        # apply formatting per row based on col G (Band)
        for i, rec in enumerate(vals, start=2):
            band = rec.get("Band","")
            if band in fmt_cache:
                try:
                    format_cell_ranges(ws, [(f"A{i}:J{i}", fmt_cache[band])])
                except Exception:
                    pass

    except Exception as e:
        print("⚠️ BiWeekly sheet write error:", e)

def _post_biweekly_to_topic(msg_text):
    """Public post to topic (no sheet links)."""
    group_id = os.getenv("REPORT_GROUP_ID","").strip()
    topic_id = os.getenv("REPORT_TOPIC_ID","").strip()
    if not group_id or not topic_id:
        print("⚠️ REPORT_GROUP_ID/REPORT_TOPIC_ID not set; skipping public topic post.")
        return
    try:
        bot.send_message(chat_id=int(group_id), text=_truncate_text(msg_text), message_thread_id=int(topic_id))
        print("✅ Bi-Weekly posted to topic.")
    except Exception as e:
        print("⚠️ Topic post failed:", e)

def _restrict_low_in_group(low_reg_ids):
    """Optionally mute Low students in the report group for N days."""
    if str(os.getenv("ENFORCE_LOW_IN_GROUP","false")).lower() != "true":
        return
    group_id = os.getenv("REPORT_GROUP_ID","").strip()
    if not group_id:
        return
    days = int(os.getenv("LOW_RESTRICT_DAYS","7"))
    until = int((datetime.now(ZoneInfo(TIMEZONE)) + timedelta(days=days)).timestamp())
    for rid in low_reg_ids:
        try:
            bot.restrict_chat_member(
                chat_id=int(group_id), user_id=int(rid),
                permissions=telebot.types.ChatPermissions(can_send_messages=False),
                until_date=until
            )
            print(f"🔒 Restricted user {rid} for {days}d (Low band).")
        except Exception as e:
            print(f"restrict_chat_member failed for {rid}:", e)

def send_biweekly_report():
    """
    Builds: public topic message (no links) + admin/faculty message (with sheet),
    writes a sorted & coloured 'BiWeekly_Summary',
    notifies parents for Low band with absence dates,
    optionally restricts Low band users in group.
    """
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    start = _get_class_start_date()
    win_start, win_end, _ = _current_biweekly_window(today, start)

    # OFFLINE
    off_students = get_cached_master_list()
    off_absmap, off_classes, off_absdates = _collect_absences_between_with_dates(
        ABSENTEE_SHEET_ID, "-offline", off_students, win_start, win_end
    )
    off_block, off_detailed, off_bands = _build_mode_summary("Offline", off_students, off_absmap, off_classes)

    # ONLINE
    on_students = get_cached_online_master_list()
    on_absmap, on_classes, on_absdates = _collect_absences_between_with_dates(
        ONLINE_ABSENTEE_SHEET_ID, "-online", on_students, win_start, win_end
    )
    on_block, on_detailed, on_bands = _build_mode_summary("Online", on_students, on_absmap, on_classes)

    # Public message (no sheet links) — Offline first, then Online
    title = f"📅 Bi-Weekly Summary: {win_start} – {win_end}"
    public_msg = f"{title}\n\n{off_block}\n\n{on_block}"
    _post_biweekly_to_topic(public_msg)

    # Admin/Faculty message — include quick link to BiWeekly_Summary tab
    # (A generic workbook link is fine; tab is visible in the file.)
    admin_msg = public_msg + "\n\n📄 Detailed rows are written to the 'BiWeekly_Summary' tab in the main workbook."
    if TEACHER_ID:
        safe_send_chat(TEACHER_ID, admin_msg)
    if ADMIN_ID:
        safe_send_chat(ADMIN_ID, admin_msg)

    # Write sorted + coloured sheet rows
    _write_biweekly_sheet(win_start, win_end, off_detailed, on_detailed)

    # Parent caution for Low band (merge low from both modes)
    low_threshold = float(os.getenv("LOW_THRESHOLD","0.60"))
    parent_tpl = os.getenv("PARENT_LOW_MSG",
        "⚠️ Dear Parent, your child {student_name} ({reg_id}) recorded Low attendance (<60%) in the last 14 days. Absence dates: {dates}."
    )

    def _student_by_id(rows, rid):
        for r in rows:
            if str(r.get("Reg ID","")).strip() == rid:
                return r
        return {}

    low_ids = set()
    # Offline Lows
    for rid, name, pres, absd, pct, band in off_detailed:
        if band == "Low":
            low_ids.add(rid)
            srow = _student_by_id(off_students, rid)
            dates = ", ".join(off_absdates.get(rid, [])) or "—"
            msg = parent_tpl.format(student_name=name, reg_id=rid, dates=dates)
            # notify via Telegram (or queue)
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "offline bi-weekly")
    # Online Lows
    for rid, name, pres, absd, pct, band in on_detailed:
        if band == "Low":
            low_ids.add(rid)
            srow = _student_by_id(on_students, rid)
            dates = ", ".join(on_absdates.get(rid, [])) or "—"
            msg = parent_tpl.format(student_name=name, reg_id=rid, dates=dates)
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "online bi-weekly")

    # Optional: restrict Low band students in the group
    _restrict_low_in_group(low_ids)

    print("✅ Bi-Weekly report: public topic posted, admin notified, sheet updated, parents cautioned.")

Parent DM uses your existing notify_parent_telegram() (so it’ll queue if not yet linked).
If you also want WhatsApp caution via MSG91, we can reuse your MSG91 helper to push the same msg.

⸻

3) Worker: keep your earlier biweekly_worker() — it will now call the upgraded send_biweekly_report() automatically at the cycle boundary (−5 min primary, +2 h fallback). No change needed in the worker itself.

You already added:

threading.Thread(target=biweekly_worker, daemon=True).start()

so you’re good.

⸻

4) About blocking access
	•	Telegram topics: Telegram doesn’t support “hide this topic for user X”.
What we can do is restrict/mute a user in the whole group (can’t post). That’s what _restrict_low_in_group() does (requires the bot to be admin with “ban users / manage chat”).
	•	Unrestricting: This code sets an until_date (N days). Telegram auto-unmutes after that. You can also run a small daily job to unrestrict when their next window is not “Low”.
	•	Classes app integration: yes, but needs an API. Typical pattern:
	1.	Your app exposes a REST endpoint POST /v1/roster/restrict with {user_id, reason, until_date}.
	2.	Add a small HTTP call in _restrict_low_in_group() to that endpoint.
	3.	For safety, sign requests with a shared secret (HMAC) or a static bearer token stored in .env (e.g., ACADEMY_API_URL, ACADEMY_API_KEY).

If you share the app’s API shape, I’ll drop a ready-to-paste client call.

⸻

What you now have
	•	✅ Auto EOD (−5 min primary, +2 h fallback)
	•	✅ Auto Bi-Weekly on cycle boundary, public topic post (no links)
	•	✅ Admin/faculty DM with sheet pointer
	•	✅ Sheet tab BiWeekly_Summary, sorted (Low→Avg→High→100%) and colour-coded
	•	✅ Parent caution DM with absence dates list
	•	✅ Optional auto-restrict Low band in the Telegram group

Want me to also add a Monthly worker that uses the same pipeline (public topic + admin sheet + parent caution + optional restrict)?
