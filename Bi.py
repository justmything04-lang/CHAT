# ---------------- Bi-Weekly helpers (public topic + admin sheet + parent caution + app lock) ----------------

def _safe_parse_date(s):
    if not s:
        return None
    # prefer dateutil if available
    if _dateparse:
        try:
            return _dateparse(str(s)).date()
        except Exception:
            pass
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None

def _get_class_start_date():
    # Prefer Settings!D2 if present; else infer earliest absentee tab date; else today
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
    """
    Window length = 14 days. Returns (win_start, win_end, is_boundary_today).
    Cycle n: [start+14n, start+14n+13]; boundary day is win_end.
    """
    days = _days_since(start_date, today_date)
    if days < 0:
        return (today_date, today_date, False)
    idx = days // 14
    win_start = start_date + timedelta(days=14*idx)
    win_end   = win_start + timedelta(days=13)
    return (win_start, win_end, today_date == win_end)

def _collect_absences_between_with_dates(sheet_key, suffix, student_rows, win_start, win_end):
    """
    Reads absentee tabs 'YYYY-MM-DD-<suffix>' within [win_start..win_end].
    Returns: abs_map {rid: absent_days}, classes count, abs_dates {rid: [YYYY-MM-DD,...]}
    """
    try:
        f = client.open_by_key(sheet_key)
        tabs = f.worksheets()
    except Exception:
        tabs = []

    day_tabs = []
    for ws in tabs:
        t = ws.title
        if not t.endswith(suffix):
            continue
        ds = t[:-len(suffix)]
        d  = _safe_parse_date(ds)
        if d and (win_start <= d <= win_end):
            day_tabs.append((d, ds, ws))

    classes = len(day_tabs)
    ids = { str(r.get("Reg ID","")).strip() for r in student_rows }
    abs_map   = { rid: 0 for rid in ids }
    abs_dates = { rid: [] for rid in ids }

    for _, ds, ws in day_tabs:
        try:
            rows = _gs_read(lambda: ws.get_all_records())
            for a in rows:
                rid = str(a.get("Reg ID","")).strip()
                if rid in abs_map:
                    abs_map[rid] += 1
                    abs_dates[rid].append(ds)
        except Exception:
            pass

    return abs_map, classes, abs_dates

def _band_for(pct):
    if pct >= 1.0:  return "100%"
    if pct >= 0.80: return "High"
    if pct >= 0.60: return "Average"
    return "Low"

def _build_mode_summary(mode_label, student_rows, abs_map, classes):
    """
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
    for _, _, _, _, _, band in detailed:
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
    # Sort: Low -> Average -> High -> 100%, then by % asc, then name
    order = {"Low":0, "Average":1, "High":2, "100%":3}
    return sorted(detailed_rows, key=lambda t: (order.get(t[5], 9), t[4], t[1].lower()))

def _write_biweekly_sheet(win_start, win_end, off_rows, on_rows):
    """
    Create a NEW tab for this bi-weekly window (‘BIW YYYY-MM-DD to YYYY-MM-DD’),
    write sorted rows, optionally color by band, and return (tab_gid, tab_title).
    Mirrors monthly/course behavior.
    """
    try:
        wb = client.open_by_key(SHEET_ID)
        base_title = f"BIW {win_start} to {win_end}"
        tab_title = _make_unique_title(wb, base_title)
        ws = wb.add_worksheet(title=tab_title, rows="2000", cols="10")
        ws.update("A1:J1", [[
            "Mode","RegID","Name","Present","Absent","Percent","Band",
            "WindowStart","WindowEnd","CreatedAt"
        ]])
        if set_frozen:
            try: set_frozen(ws, rows=1)
            except Exception: pass

        off_sorted = _sorted_by_band(off_rows)
        on_sorted  = _sorted_by_band(on_rows)

        def _fmt(mode, r):
            rid,name,pres,absd,pct,band = r
            return [mode,rid,name,pres,absd,round(pct*100,1),
                    band,str(win_start),str(win_end),now_ts()]

        rows_to_write = [_fmt("Offline",r) for r in off_sorted] + \
                        [_fmt("Online",r) for r in on_sorted]
        if rows_to_write:
            ws.append_rows(rows_to_write,value_input_option='USER_ENTERED')

        # --- optional colour formatting ---
        if format_cell_ranges and Color and CellFormat:
            try:
                vals = ws.get_all_records()
                colors = {
                    "Low":     Color(1,0.8,0.8),
                    "Average": Color(1,1,0.8),
                    "High":    Color(0.85,1,0.85),
                    "100%":    Color(0.85,0.9,1)
                }
                fmts = {k: CellFormat(backgroundColor=v,
                        textFormat=TextFormat(bold=False)) for k,v in colors.items()}
                for i,rec in enumerate(vals,start=2):
                    band = rec.get("Band","")
                    if band in fmts:
                        try: format_cell_ranges(ws,[(f"A{i}:J{i}",fmts[band])])
                        except Exception: pass
            except Exception as e:
                print("Colouring skipped for biweekly:",e)

        return ws.id,tab_title
    except Exception as e:
        print("⚠️ BiWeekly sheet create/write error:",e)
        return None,None


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

def _enforce_low_in_app(low_reg_ids, win_start, win_end):
    """
    Call academy API to deny live/backup access for Low band.
    No Telegram restriction is applied.
    """
    if str(os.getenv("ENFORCE_LOW_IN_APP","false")).lower() != "true":
        return
    url = (os.getenv("ACADEMY_API_URL") or "").strip()
    key = (os.getenv("ACADEMY_API_KEY") or "").strip()
    if not (url and key):
        print("⚠️ Academy app URL/KEY missing; skip Low enforcement.")
        return
    payload = {
        "window_start": str(win_start),
        "window_end": str(win_end),
        "reason": "low_attendance_14d",
        "user_ids": list(low_reg_ids)  # reg_id == telegram user_id in your system
    }
    try:
        r = requests.post(url, json=payload, headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"}, timeout=20)
        print("📤 Academy lock req:", payload)
        print("📥 Academy lock resp:", r.status_code, (r.text or "")[:400])
    except Exception as e:
        print("⚠️ Academy lock call failed:", e)

def send_biweekly_report():
    """
    Public topic (no links) + admin DM + sheet write (sorted & coloured) + parent caution
    + Academy-app lock for Low band.
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

    # Public message (no sheet links) — Offline then Online
    title = f"📅 Bi-Weekly Summary: {win_start} – {win_end}"
    public_msg = f"{title}\n\n{off_block}\n\n{on_block}"
    _post_biweekly_to_topic(public_msg)

    # Write to sheet (create new tab) and get gid + title
    tab_gid, tab_title = _write_biweekly_sheet(win_start, win_end, off_detailed, on_detailed)

    # Admin/Faculty message (build link if we got gid)
    if tab_gid:
        sheet_link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={tab_gid}"
        admin_msg = public_msg + f"\n\n📄 Detailed rows are in: {tab_title}\n🔗 {sheet_link}"
    else:
        admin_msg = public_msg + "\n\n📄 Detailed rows are in the 'BiWeekly_Summary' (or check Reports workbook)."

    if TEACHER_ID:
        safe_send_chat(TEACHER_ID, admin_msg)
    if ADMIN_ID:
        safe_send_chat(ADMIN_ID, admin_msg)

    # Parent caution for Low band (DM via Telegram; will queue if parent not linked)
    parent_tpl = os.getenv("PARENT_LOW_MSG",
        "⚠️ Dear Parent, your child {student_name} ({reg_id}) recorded Low attendance (<60%) in the last 14 days. Absence dates: {dates}."
    )

    def _by_id(rows, rid):
        for r in rows:
            if str(r.get("Reg ID","")).strip() == rid:
                return r
        return {}

    low_ids = set()

    for rid, name, pres, absd, pct, band in off_detailed:
        if band == "Low":
            low_ids.add(rid)
            dates = ", ".join(off_absdates.get(rid, [])) or "—"
            # reuse existing notifier (queues if not linked)
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "offline bi-weekly")

    for rid, name, pres, absd, pct, band in on_detailed:
        if band == "Low":
            low_ids.add(rid)
            dates = ", ".join(on_absdates.get(rid, [])) or "—"
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "online bi-weekly")

    # Deny live/backup in Academy app for Low band
    _enforce_low_in_app(low_ids, win_start, win_end)

   
    # Write to sheet (sorted + coloured)
    _write_biweekly_sheet(win_start, win_end, off_detailed, on_detailed)

    # Parent caution for Low band (DM via Telegram; will queue if parent not linked)
    parent_tpl = os.getenv("PARENT_LOW_MSG",
        "⚠️ Dear Parent, your child {student_name} ({reg_id}) recorded Low attendance (<60%) in the last 14 days. Absence dates: {dates}."
    )

    def _by_id(rows, rid):
        for r in rows:
            if str(r.get("Reg ID","")).strip() == rid:
                return r
        return {}

    low_ids = set()

    for rid, name, pres, absd, pct, band in off_detailed:
        if band == "Low":
            low_ids.add(rid)
            dates = ", ".join(off_absdates.get(rid, [])) or "—"
            # reuse existing notifier (queues if not linked)
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "offline bi-weekly")
            # You could also send WhatsApp via MSG91 here using your helper, if needed.

    for rid, name, pres, absd, pct, band in on_detailed:
        if band == "Low":
            low_ids.add(rid)
            dates = ", ".join(on_absdates.get(rid, [])) or "—"
            notify_parent_telegram(rid, name, f"{win_start}–{win_end}", "online bi-weekly")

    # Deny live/backup in Academy app for Low band
    _enforce_low_in_app(low_ids, win_start, win_end)

    print("✅ Bi-Weekly: topic posted, admin notified, sheet updated, parents cautioned, app lock attempted.")


    # --- Auto-publish Top 3 for manual and worker Bi-Weekly ---
    try:
        publish_top3_to_teacher_and_topic()
    except Exception as e:
        print("Bi-Weekly -> Top3 publish error (send_biweekly_report):",e)
        if ADMIN_ID:
            safe_send_chat(ADMIN_ID, f"⚠️ Bi-Weekly Top3 publish failed: {e}")


# ---------------- Monthly & Course helpers (public topic + admin tab link + risk watch + parent caution) ----------------

def _month_window_for(date_obj):
    y, m = date_obj.year, date_obj.month
    first = datetime(y, m, 1, tzinfo=ZoneInfo(TIMEZONE)).date()
    last_day = calendar.monthrange(y, m)[1]
    last = datetime(y, m, last_day, tzinfo=ZoneInfo(TIMEZONE)).date()
    return first, last

def _collect_absences_between(sheet_key, suffix, student_rows, win_start, win_end):
    # thin wrapper to use the bi-weekly collector you already have
    return _collect_absences_between_with_dates(sheet_key, suffix, student_rows, win_start, win_end)

def _risk_band_for(pct, risk_threshold):
    return "Risk" if pct <= risk_threshold else None

def _make_unique_title(wb, base_title):
    """
    Ensures a new tab is created each time:
    - If base title is free -> use it
    - Else append timestamp suffix: 'base HHMMSS'
    """
    try:
        titles = [ws.title for ws in wb.worksheets()]
    except Exception:
        titles = []
    if base_title not in titles:
        return base_title
    suffix = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H%M%S")
    return f"{base_title} {suffix}"

def _write_monthly_sheet(win_start, win_end, off_rows, on_rows):
    """
    Always creates a NEW tab: 'MON YYYY-MM' (or with HHMMSS if repeated).
    Columns: Mode, RegID, Name, Present, Absent, Percent, Band, WindowStart, WindowEnd, CreatedAt
    Returns: (tab_gid, tab_title)
    """
    wb = client.open_by_key(SHEET_ID)
    base_title = f"MON {win_start.strftime('%Y-%m')}"
    tab_title = _make_unique_title(wb, base_title)
    ws = wb.add_worksheet(title=tab_title, rows="4000", cols="10")
    ws.update("A1:J1", [[
        "Mode","RegID","Name","Present","Absent","Percent","Band",
        "WindowStart","WindowEnd","CreatedAt"
    ]])
    if set_frozen:
        try: set_frozen(ws, rows=1)
        except Exception: pass

    off_sorted = _sorted_by_band(off_rows)
    on_sorted  = _sorted_by_band(on_rows)

    def _fmt(mode, r):
        rid, name, pres, absd, pct, band = r
        return [mode, rid, name, pres, absd, round(pct*100,1), band, str(win_start), str(win_end), now_ts()]

    rows_to_write = [_fmt("Offline", r) for r in off_sorted] + [_fmt("Online", r) for r in on_sorted]
    if rows_to_write:
        ws.append_rows(rows_to_write, value_input_option='USER_ENTERED')

    # optional colours (same as bi-weekly)
    if format_cell_ranges and Color and CellFormat:
        try:
            vals = ws.get_all_records()
            colors = {
                "Low":     Color(1, 0.8, 0.8),   # (we use bi-weekly band names)
                "Average": Color(1, 1, 0.8),
                "High":    Color(0.85, 1, 0.85),
                "100%":    Color(0.85, 0.90, 1)
            }
            fmt_cache = {k: CellFormat(backgroundColor=v, textFormat=TextFormat(bold=False)) for k, v in colors.items()}
            for i, rec in enumerate(vals, start=2):
                band = rec.get("Band","")
                if band in fmt_cache:
                    try:
                        format_cell_ranges(ws, [(f"A{i}:J{i}", fmt_cache[band])])
                    except Exception:
                        pass
        except Exception as e:
            print("Colouring skipped:", e)

    return ws.id, tab_title

def _write_course_sheet(win_start, win_end, off_rows, on_rows):
    """
    Always creates a NEW tab: 'COURSE start_to_end' (with HHMMSS if duplicate).
    Returns (tab_gid, tab_title) and applies colour coding like bi-weekly/monthly.
    """
    wb = client.open_by_key(SHEET_ID)
    base_title = f"COURSE {win_start} to {win_end}"
    tab_title = _make_unique_title(wb, base_title)
    ws = wb.add_worksheet(title=tab_title, rows="6000", cols="10")
    ws.update("A1:J1", [[
        "Mode","RegID","Name","Present","Absent","Percent","Band",
        "WindowStart","WindowEnd","CreatedAt"
    ]])
    if set_frozen:
        try: set_frozen(ws, rows=1)
        except Exception: pass

    off_sorted = _sorted_by_band(off_rows)
    on_sorted  = _sorted_by_band(on_rows)

    def _fmt(mode, r):
        rid,name,pres,absd,pct,band = r
        return [mode,rid,name,pres,absd,round(pct*100,1),
                band,str(win_start),str(win_end),now_ts()]

    rows_to_write = [_fmt("Offline",r) for r in off_sorted] + \
                    [_fmt("Online",r) for r in on_sorted]
    if rows_to_write:
        ws.append_rows(rows_to_write,value_input_option='USER_ENTERED')

    # --- colour bands ---
    if format_cell_ranges and Color and CellFormat:
        try:
            vals = ws.get_all_records()
            colors = {
                "Low":Color(1,0.8,0.8),
                "Average":Color(1,1,0.8),
                "High":Color(0.85,1,0.85),
                "100%":Color(0.85,0.9,1)
            }
            fmts={k:CellFormat(backgroundColor=v,
                 textFormat=TextFormat(bold=False)) for k,v in colors.items()}
            for i,rec in enumerate(vals,start=2):
                band=rec.get("Band","")
                if band in fmts:
                    try: format_cell_ranges(ws,[(f"A{i}:J{i}",fmts[band])])
                    except Exception: pass
        except Exception as e:
            print("Colouring skipped for course summary:",e)

    return ws.id, tab_title

def _post_public(msg_text):
    group_id = os.getenv("REPORT_GROUP_ID","").strip()
    topic_id = os.getenv("REPORT_TOPIC_ID","").strip()
    if not group_id or not topic_id:
        print("⚠️ REPORT_GROUP_ID/REPORT_TOPIC_ID not set; skipping public topic post.")
        return
    try:
        bot.send_message(chat_id=int(group_id), text=_truncate_text(msg_text), message_thread_id=int(topic_id))
    except Exception as e:
        print("⚠️ Public post failed:", e)

def _send_parent_risk_alerts(risk_list, abs_dates_map, window_label):
    # risk_list is a list of tuples (rid, name, pres, absd, pct, band)
    tpl = os.getenv("PARENT_RISK_MSG",
        "⚠️ Dear Parent, your child {student_name} ({reg_id}) is at risk (≤50%) for {window_label}. Absence dates: {dates}."
    )
    for rid, name, pres, absd, pct, band in risk_list:
        dates = ", ".join(abs_dates_map.get(rid, [])) or "—"
        # reuse your Telegram notifier (queues if not linked)
        # send a concise window label in the date slot
        try:
            msg = tpl.format(student_name=name, reg_id=rid, window_label=window_label, dates=dates)
            # deliver via Telegram parent queue path:
            # here we pass window_label in 'date' slot just to reuse the same function signature
            notify_parent_telegram(rid, name, window_label, "risk")
        except Exception as e:
            print("Parent risk DM build error:", e)

def send_monthly_report():
    """
    Auto/manual monthly report.
    Window: first..last day of current month (auto on last day), or first..today (if run mid-month).
    Creates a NEW tab and DMs faculty/admin with direct tab link (gid).
    Public topic gets clean counts and Risk Watch.
    """
    now_local = datetime.now(ZoneInfo(TIMEZONE)).date()
    m_first, m_last = _month_window_for(now_local)
    # if run mid-month manually, use first..today to avoid empty future days
    win_end = m_last if now_local == m_last else now_local
    win_start = m_first
    risk_threshold = float(os.getenv("RISK_THRESHOLD","0.50"))

    # collect
    off_students = get_cached_master_list()
    on_students  = get_cached_online_master_list()
    off_absmap, off_classes, off_absdates = _collect_absences_between(ABSENTEE_SHEET_ID, "-offline", off_students, win_start, win_end)
    on_absmap,  on_classes,  on_absdates  = _collect_absences_between(ONLINE_ABSENTEE_SHEET_ID, "-online",  on_students,  win_start, win_end)

    # detail rows + bands
    off_block, off_detailed, _ = _build_mode_summary("Offline", off_students, off_absmap, off_classes)
    on_block,  on_detailed,  _ = _build_mode_summary("Online",  on_students,  on_absmap,  on_classes)

    # Risk Watch (≤50%)
    def _riskify(rows):
        out = []
        for rid, name, pres, absd, pct, band in rows:
            if pct <= risk_threshold:
                out.append((rid, name, pres, absd, pct, band))
        return out
    risk_off = _riskify(off_detailed)
    risk_on  = _riskify(on_detailed)
    risk_total = len(risk_off) + len(risk_on)

    # sheet write (new tab)
    tab_gid, tab_title = _write_monthly_sheet(win_start, win_end, off_detailed, on_detailed)
    link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={tab_gid}"

    # messages
    title = f"📅 Monthly Summary: {win_start} – {win_end}"
    public_msg = f"{title}\n\n{off_block}\n\n{on_block}\n\n🚩 Risk Watch (≤{int(risk_threshold*100)}%): {risk_total}"
    _post_public(public_msg)

    admin_msg = public_msg + f"\n\n📄 Tab: {tab_title}\n🔗 {link}"
    if TEACHER_ID: safe_send_chat(TEACHER_ID, admin_msg)
    if ADMIN_ID:   safe_send_chat(ADMIN_ID,   admin_msg)

    # parent cautions for Risk
    window_label = f"Monthly {win_start}–{win_end}"
    _send_parent_risk_alerts(risk_off, off_absdates, window_label)
    _send_parent_risk_alerts(risk_on,  on_absdates,  window_label)

    # optional: academy app lock (monthly)

    _enforce_low_in_app({rid for rid, *_ in (risk_off + risk_on)}, win_start, win_end)

    # --- Auto-publish Top 3 together with Monthly ---
    try:
        publish_top3_to_teacher_and_topic()
    except Exception as e:
        print("Monthly -> Top3 publish error (send_monthly_report):",e)
        if ADMIN_ID:
            safe_send_chat(ADMIN_ID, f"⚠️ Monthly Top3 publish failed: {e}")

    print("✅ Monthly report done.")

def send_course_summary_report():
    """
    Full-course window: from class start (Settings!D2 or earliest tab) till today.
    Creates a NEW tab and DMs link; public post shows counts + risk watch.
    """
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    start = _get_class_start_date()
    win_start, win_end = start, today
    risk_threshold = float(os.getenv("RISK_THRESHOLD","0.50"))

    off_students = get_cached_master_list()
    on_students  = get_cached_online_master_list()
    off_absmap, off_classes, off_absdates = _collect_absences_between(ABSENTEE_SHEET_ID, "-offline", off_students, win_start, win_end)
    on_absmap,  on_classes,  on_absdates  = _collect_absences_between(ONLINE_ABSENTEE_SHEET_ID, "-online",  on_students,  win_start, win_end)

    off_block, off_detailed, _ = _build_mode_summary("Offline", off_students, off_absmap, off_classes)
    on_block,  on_detailed,  _ = _build_mode_summary("Online",  on_students,  on_absmap,  on_classes)

    def _riskify(rows):
        return [t for t in rows if t[4] <= risk_threshold]
    risk_off = _riskify(off_detailed)
    risk_on  = _riskify(on_detailed)
    risk_total = len(risk_off) + len(risk_on)

    tab_gid, tab_title = _write_course_sheet(win_start, win_end, off_detailed, on_detailed)
    link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={tab_gid}"

    title = f"📘 Course Summary: {win_start} – {win_end}"
    public_msg = f"{title}\n\n{off_block}\n\n{on_block}\n\n🚩 Risk Watch (≤{int(risk_threshold*100)}%): {risk_total}"
    _post_public(public_msg)

    admin_msg = public_msg + f"\n\n📄 Tab: {tab_title}\n🔗 {link}"
    if TEACHER_ID: safe_send_chat(TEACHER_ID, admin_msg)
    if ADMIN_ID:   safe_send_chat(ADMIN_ID,   admin_msg)

    window_label = f"Course {win_start}–{win_end}"
    _send_parent_risk_alerts(risk_off, off_absdates, window_label)
    _send_parent_risk_alerts(risk_on,  on_absdates,  window_label)

    _enforce_low_in_app({rid for rid, *_ in (risk_off + risk_on)}, win_start, win_end)

    try:
        publish_top3_to_teacher_and_topic()
    except Exception as e:
        print("Course Summary -> Top3 publish error:", e)

    print("✅ Course summary done.")

# ---------------- Join Request Guard ----------------
@bot.chat_join_request_handler(func=lambda req: True)
def handle_join_request(req):
    """
    Approves the join request only if:
      - The invite link is one we created, AND
      - The request.user.id matches the UserId we stored for that link, AND
      - Status is ACTIVE and not expired.
    Else declines.
    """
    try:
        inv = req.invite_link.invite_link if req.invite_link else ""
        row_idx, rec = invites_find_by_link(inv)
        if not row_idx or not rec:
            print("join_request: invite not recognized", inv)
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        status = str(rec.get("Status","")).upper()
        intended_uid = str(rec.get("UserId","")).strip()
        grp = int(rec.get("GroupId", req.chat.id))
        expire_at = str(rec.get("ExpireAt","")).strip()

        # expiry check (if set)
        if expire_at:
            try:
                exp = datetime.strptime(expire_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(TIMEZONE))
                if datetime.now(ZoneInfo(TIMEZONE)) > exp:
                    print("join_request: invite expired")
                    bot.decline_chat_join_request(req.chat.id, req.from_user.id)
                    return
            except Exception:
                pass

        if status != "ACTIVE":
            print("join_request: invite not active")
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        if str(req.from_user.id) != intended_uid:
            print(f"join_request: user mismatch expected={intended_uid} got={req.from_user.id}")
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        # All good → approve and mark USED
        bot.approve_chat_join_request(grp, req.from_user.id)
        invites_mark_used(row_idx)
        print(f"✅ Approved {req.from_user.id} via guarded invite.")
    except Exception as e:
        print("handle_join_request error:", e)
        try:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception:
            pass

# Inline button handler: refresh one-time invite in-place (only student may press)
@bot.callback_query_handler(func=lambda c: isinstance(c.data, str) and c.data.startswith("newlink:"))
def _callback_newlink(c):
    """
    Callback data format: newlink:{reg_id}
    Only the student with reg_id can use the button. If the student is already in the group,
    we inform them and remove the button. Otherwise create a fresh one-time invite and edit the same message.
    """
    try:
        parts = c.data.split(":", 1)
        if len(parts) != 2:
            bot.answer_callback_query(c.id, "Invalid request.")
            return
        reg_id = parts[1].strip()
        requester = str(c.from_user.id)
        # Only the student themselves (or teacher/admin) can refresh their link
        if requester != str(reg_id) and not (str(requester) == str(TEACHER_ID) or (ADMIN_ID and str(requester) == str(ADMIN_ID))):
            bot.answer_callback_query(c.id, "This button is only usable by the invited student.", show_alert=True)
            return

        # Determine group id (where invite links are issued). Use env BATCH_GROUP_ID if set.
        try:
            group_id = int(os.getenv("BATCH_GROUP_ID", "0") or "0")
        except Exception:
            group_id = 0

        # If group_id available, check membership first
        already_member = False
        if group_id:
            try:
                member = bot.get_chat_member(chat_id=group_id, user_id=int(reg_id))
                status = getattr(member, "status", "")
                if status and str(status).lower() in ("member", "creator", "administrator"):
                    already_member = True
            except Exception:
                # could be RateLimit or user not found — ignore and proceed to safe path
                pass

        if already_member:
            # Edit message to remove the button and show the "already a member" note
            try:
                bot.edit_message_text(
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id,
                    text=_truncate_text(f"✅ You are already in the group. No new link is needed.")
                )
            except Exception:
                pass
            bot.answer_callback_query(c.id, "You are already in the group.", show_alert=True)
            return

        # Not a member -> create a fresh one-time invite and replace the link in the same message
        try:
            new_link = create_one_time_invite_for(int(reg_id), kind="student")
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔁 New link", callback_data=f"newlink:{reg_id}"))
            new_text = (
                "✅ Here is your refreshed one-time group invite (only you can use it):\n\n"
                f"{new_link}\n\n"
                "Click to join the class group. 👋"
            )
            try:
                bot.edit_message_text(chat_id=c.message.chat.id, message_id=c.message.message_id,
                                      text=new_text, reply_markup=kb)
            except Exception:
                # fallback: at least answer the callback with the link (non-spammy)
                bot.answer_callback_query(c.id, f"New link: {new_link}")
                return
            bot.answer_callback_query(c.id, "✅ New link created.", show_alert=False)
        except Exception as e:
            print("⚠️ newlink callback failed:", e)
            try:
                bot.answer_callback_query(c.id, "⚠️ Could not create new link right now. Try again later.", show_alert=True)
            except Exception:
                pass




# ---------------- Background workers ----------------

def _is_eod_done_for(today_str):
    """Returns True if today's offline+online absentee tabs already exist."""
    try:
        off_file = client.open_by_key(ABSENTEE_SHEET_ID)
        on_file  = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        off_done = any(ws.title == f"{today_str}-offline" for ws in off_file.worksheets())
        on_done  = any(ws.title == f"{today_str}-online"  for ws in on_file.worksheets())
        return off_done and on_done
    except Exception as e:
        print("_is_eod_done_for check failed:", e)
        return False

def auto_eod_worker():
    """
    Checks every 2 minutes.
    Triggers EOD 5 minutes BEFORE EndTime (primary), and
    if still not done, triggers again 2 hours AFTER EndTime (fallback).
    Uses sheet-tab existence and Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            s = get_cached_settings()
            end_str = s.get("EndTime", "23:59").strip()
            today   = get_today_date()

            # build today's localized end time
            try:
                end_dt = datetime.strptime(today + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = datetime.now(ZoneInfo(TIMEZONE))

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)
            now_local       = datetime.now(ZoneInfo(TIMEZONE))

            # persistent guard: check if we already ran EOD today (control key)
            last_eod = _control_get("LastEOD") or ""
            if last_eod == today:
                time.sleep(120)
                continue

            # also fallback to sheet-existence check (safe)
            if _is_eod_done_for(today):
                # mark control so other instances don't also run
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Auto EOD (primary, -5 min) window…")
                # run and mark
                generate_eod_and_notify()
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Auto EOD (fallback, +2h) window…")
                if not _is_eod_done_for(today):
                    generate_eod_and_notify()
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            time.sleep(120)

        except Exception as e:
            print("auto_eod_worker error:", e)
            time.sleep(180)


def biweekly_worker():
    """
    Checks every 2 minutes.
    On the LAST day of the current 14-day window:
      - trigger 5 minutes BEFORE EndTime (primary)
      - if missed, fallback 2 hours AFTER EndTime
    Uses Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            today     = now_local.date()

            start = _get_class_start_date()
            win_start, win_end, is_boundary = _current_biweekly_window(today, start)

            if not is_boundary:
                time.sleep(120)
                continue

            key = f"BiWeekly_{win_end}"
            last = _control_get("LastBiWeekly") or ""
            if last == str(win_end):
                time.sleep(120)
                continue

            s = get_cached_settings()
            end_str = s.get("EndTime","23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Bi-Weekly (primary, -5 min) window…")
                send_biweekly_report()
                _control_set("LastBiWeekly", str(win_end))
                # publish Top3 together with Bi-Weekly
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Bi-Weekly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Bi-Weekly (fallback, +2h) window…")
                send_biweekly_report()
                _control_set("LastBiWeekly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Bi-Weekly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            time.sleep(120)
        except Exception as e:
            print("biweekly_worker error:", e)
            time.sleep(180)


def _is_last_day_of_month(d):
    return d.day == calendar.monthrange(d.year, d.month)[1]

def monthly_worker():
    """
    Checks every 2 minutes.
    Trigger when 30-day window ends (30 days after class start cycle), using Settings start date as anchor.
    Uses Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            today     = now_local.date()

            start = _get_class_start_date()
            # compute 30-day windows:
            days = _days_since(start, today)
            if days < 0:
                time.sleep(120); continue
            idx = days // 30
            win_start = start + timedelta(days=30*idx)
            win_end = win_start + timedelta(days=29)  # 30-day window inclusive
            is_boundary = (today == win_end)

            if not is_boundary:
                time.sleep(120)
                continue

            key = f"Monthly_{win_end.strftime('%Y-%m-%d')}"
            last = _control_get("LastMonthly") or ""
            if last == str(win_end):
                time.sleep(120)
                continue

            s = get_cached_settings()
            end_str = s.get("EndTime","23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Monthly (primary, -5 min) window…")
                send_monthly_report()
                _control_set("LastMonthly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Monthly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Monthly (fallback, +2h) window…")
                send_monthly_report()
                _control_set("LastMonthly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Monthly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            time.sleep(120)
        except Exception as e:
            print("monthly_worker error:", e)
            time.sleep(180)


def parent_queue_retry_worker():
    """Try to deliver pending parent notifications once a day."""
    while True:
        try:
            pending = parentqueue_list_pending()
            if not pending:
                time.sleep(3600*6)  # sleep 6h if none
                continue

            # For each pending, if parent linked now -> send
            for row_idx, r in pending:
                reg_id = str(r.get("RegID","")).strip()
                sheet, mode = find_sheet_for_reg(reg_id)
                info = get_parent_info(sheet, reg_id) if sheet else {}
                chatid = info.get("ParentChatId","").strip()
                linked = info.get("ParentLinked","").strip().lower() == "yes"
                if chatid and linked:
                    try:
                        safe_send_chat(chatid, r.get("Message",""))
                        parentqueue_mark_sent(row_idx)
                    except Exception as e:
                        print("parent_queue_retry send error:", e)
                        parentqueue_bump_attempt(row_idx)
                else:
                    parentqueue_bump_attempt(row_idx)

            time.sleep(3600*24)  # 24 hours
        except Exception as e:
            print("parent_queue_retry_worker error:", e)
            time.sleep(3600*6)

def weekly_summary_worker():
    while True:
        try:
            now = datetime.now(ZoneInfo(TIMEZONE))
            # Sunday ~09:00 window
            if now.weekday() == 6 and now.hour == 9 and now.minute < 5:
                last_week = _control_get("LastWeekly") or ""
                this_key = now.strftime("%Y-%U")  # year-week key
                if last_week != this_key:
                    off_list = master_sheet.get_all_records()
                    on_list = online_master_sheet.get_all_records() if online_master_sheet else []

                    off_total = len(off_list)
                    on_total = len(on_list)
                    off_linked = sum(1 for r in off_list if str(r.get("ParentChatId","")).strip())
                    on_linked  = sum(1 for r in on_list if str(r.get("ParentChatId","")).strip())

                    msg = TPL_FACULTY_WEEKLY.format(
                        off_linked=off_linked, off_total=off_total,
                        on_linked=on_linked, on_total=on_total
                    )
                    if TEACHER_ID:
                        safe_send_chat(TEACHER_ID, msg)

                    # publish Top3 on Sunday too
                    try:
                        publish_top3_to_teacher_and_topic()
                    except Exception as e:
                        print("Weekly -> Top3 publish error:", e)

                    _control_set("LastWeekly", this_key)
            time.sleep(300)
        except Exception as e:
            print("Weekly summary error:", e)
            time.sleep(600)

threading.Thread(target=auto_eod_worker, daemon=True).start()
threading.Thread(target=parent_queue_retry_worker, daemon=True).start()
threading.Thread(target=weekly_summary_worker, daemon=True).start()
threading.Thread(target=biweekly_worker, daemon=True).start()
threading.Thread(target=monthly_worker, daemon=True).start()


# ---------------- Flask server (Render) ----------------
app = Flask(__name__)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", f"https://{RENDER_URL}/{BOT_TOKEN}" if RENDER_URL else "")

@app.route('/', methods=['GET'])
def home():
    return "✅ Attendance Bot (Render) — live", 200




@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.data.decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("⚠️ Webhook error:", e)
        return "Error", 500

def keep_alive():
    if not RENDER_URL and not KEEP_ALIVE_URL:
        print("⚠️ No keep-alive configured; skipping pinger.")
        return
    url_to_ping = KEEP_ALIVE_URL or f"https://{RENDER_URL}/"
    while True:
        try:
            requests.get(url_to_ping, timeout=10)
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
            print("🔁 Keep-alive ping sent.")
        except Exception as e:
            print("⚠️ Keep-alive ping failed:", e)
        time.sleep(300)

# ---------------- Start ----------------
if __name__ == "__main__":
    print("🤖 Bot starting...")
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            print(f"✅ Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            print("❌ Failed to set webhook:", e)

    threading.Thread(target=keep_alive, daemon=True).start()
    reset_attendance_if_new_day()
    load_marked_ids_from_sheet()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
