# ---------------- /eod (offline + online + parent notify) ----------------
def generate_eod_and_notify():
    """Core EOD logic used by /eod and auto-EOD worker"""
    # Flush any pending queue rows first
    with _queue_lock:
        batch = []
        while write_queue:
            batch.append(write_queue.popleft())
    if batch:
        offline_rows = [r for mode, r in batch if mode == "offline"]
        online_rows = [r for mode, r in batch if mode == "online"]
        if offline_rows:
            attendance_sheet.append_rows(offline_rows, value_input_option='USER_ENTERED')
            invalidate_cache("attendance_rows")
        if online_rows and online_attendance_sheet:
            online_attendance_sheet.append_rows(online_rows, value_input_option='USER_ENTERED')
            invalidate_cache("online_attendance_rows")

    today = get_today_date()

    # --- OFFLINE ---
    attendance_rows = get_cached_attendance_rows()
    present_ids = {str(r.get("Reg ID", "")).strip() for r in attendance_rows}
    all_students = get_cached_master_list()
    absentees = [s for s in all_students if str(s.get("Reg ID", "")).strip() not in present_ids]
    offline_file = client.open_by_key(ABSENTEE_SHEET_ID)
    try:
        ws_off = offline_file.worksheet(f"{today}-offline")
    except gspread.exceptions.WorksheetNotFound:
        ws_off = offline_file.add_worksheet(title=f"{today}-offline", rows="500", cols="3")
        ws_off.update("A1:C1", [["Name", "Reg ID", "Date"]])
    ws_off.batch_clear(["A2:C"])
    if absentees:
        rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees]
        ws_off.append_rows(rows_to_write, value_input_option='USER_ENTERED')
        # Notify parents for OFFLINE
        for s in absentees:
            notify_parent_telegram(str(s.get("Reg ID","")), s.get("Name",""), today, "offline")

    # --- ONLINE ---
    online_rows = get_cached_online_attendance_rows()
    present_online_ids = {str(r.get("Reg ID", "")).strip() for r in online_rows}
    all_online_students = get_cached_online_master_list()
    absentees_online = [s for s in all_online_students if str(s.get("Reg ID", "")).strip() not in present_online_ids]

    online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
    try:
        ws_on = online_file.worksheet(f"{today}-online")
    except gspread.exceptions.WorksheetNotFound:
        ws_on = online_file.add_worksheet(title=f"{today}-online", rows="500", cols="3")
        ws_on.update("A1:C1", [["Name", "Reg ID", "Date"]])
    ws_on.batch_clear(["A2:C"])
    if absentees_online:
        rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees_online]
        ws_on.append_rows(rows_to_write, value_input_option='USER_ENTERED')
        # Notify parents for ONLINE
        for s in absentees_online:
            notify_parent_telegram(str(s.get("Reg ID","")), s.get("Name",""), today, "online")

    # after finishing absentee sheets + parent notifications
    off_abs = len(absentees)
    on_abs = len(absentees_online)
    off_present = len(present_ids)
    on_present = len(present_online_ids)

    public = (
        f"📊 Attendance Report for {today}\n\n"
        f"📍 Offline: ✅ {off_present} / ❌ {off_abs}\n"
        f"🌐 Online:  ✅ {on_present} / ❌ {on_abs}"
    )
    _post_public(public)   # <-- no links for the topic

            

    return off_abs, on_abs, off_present, on_present, len(absentees), len(absentees_online), len(present_ids), len(present_online_ids)
