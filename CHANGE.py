Take this my eod and top 3 code change it and give me correct eod and top 3 so that i will just paste it “ # ---------------- /eod (offline + online) ----------------
@bot.message_handler(commands=['eod'])
def send_report(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        # Flush pending queue first (attempt)
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

        # OFFLINE report
        attendance_rows = get_cached_attendance_rows()
        present_ids = {str(r.get("Reg ID", "")).strip() for r in attendance_rows}
        all_students = get_cached_master_list()
        absentees = [s for s in all_students if str(s.get("Reg ID", "")).strip() not in present_ids]
        today = get_today_date()
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)
        try:
            absentee_ws_off = absentee_file.worksheet(f"{today}-offline")
        except gspread.exceptions.WorksheetNotFound:
            absentee_ws_off = absentee_file.add_worksheet(title=f"{today}-offline", rows="500", cols="3")
            absentee_ws_off.update("A1:C1", [["Name", "Reg ID", "Date"]])
        # clear then write
        if absentee_ws_off.get_all_records():
            absentee_ws_off.batch_clear(["A2:C"])
        if absentees:
            rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees]
            absentee_ws_off.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        # ONLINE report
        absentee_file_online = client.open_by_key(ABSENTEE_SHEET_ID)
        online_att_rows = get_cached_online_attendance_rows()
        present_online_ids = {str(r.get("Reg ID", "")).strip() for r in online_att_rows}
        all_online_students = get_cached_online_master_list()
        absentees_online = [s for s in all_online_students if str(s.get("Reg ID", "")).strip() not in present_online_ids]
        try:
            absentee_ws_on = absentee_file_online.worksheet(f"{today}-online")
        except gspread.exceptions.WorksheetNotFound:
            absentee_ws_on = absentee_file_online.add_worksheet(title=f"{today}-online", rows="500", cols="3")
            absentee_ws_on.update("A1:C1", [["Name", "Reg ID", "Date"]])
        if absentee_ws_on.get_all_records():
            absentee_ws_on.batch_clear(["A2:C"])
        if absentees_online:
            rows_to_write = [[s.get("Name",""), s.get("Reg ID",""), today] for s in absentees_online]
            absentee_ws_on.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        report = f"📊 Attendance Report for {today}\n\nOffline: ✅ Present {len(present_ids)} / ❌ Absent {len(absentees)}\nOnline: ✅ Present {len(present_online_ids)} / ❌ Absent {len(absentees_online)}"
        sheet_link = f"https://docs.google.com/spreadsheets/d/{ABSENTEE_SHEET_ID}/edit#gid=0"
        safe_reply(message, f"{report}\n\n📄 Absentee Sheets: {sheet_link}")
        print(f"EOD generated for {today}. offline_absent={len(absentees)}, online_absent={len(absentees_online)}")
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating report: {e}")
        print("EOD error:", e)

# ---------------- /top3 (offline + online) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        # OFFLINE top3
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)
        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        total_off_classes = len(offline_tabs)
        if total_off_classes == 0:
            off_msg = "⚠️ No offline attendance history yet."
        else:
            all_students = get_cached_master_list()
            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in all_students}
            for ws in offline_tabs:
                absentees = ws.get_all_records()
                for a in absentees:
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1
            results = []
            for reg_id, data in stats.items():
                absent = data["Absent"]
                present = total_off_classes - absent
                percent = (present / total_off_classes) * 100 if total_off_classes else 0
                results.append((data["Name"], reg_id, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))
            off_msg = f"🏆 Offline Top Performers (out of {total_off_classes} classes):\n\n"
            rank = 1
            prev_percent = None
            for name, reg, present, absent, percent in results:
                if prev_percent is None or percent < prev_percent:
                    if rank > 3:
                        break
                    prev_percent = percent
                off_msg += f"{rank}. {name} ({reg}) - ✅ {present}, ❌ {absent}, 📊 {percent:.1f}%\n"
                rank += 1

        # ONLINE top3
        online_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-online")]
        total_on_classes = len(online_tabs)
        if total_on_classes == 0:
            on_msg = "⚠️ No online attendance history yet."
        else:
            all_students_on = get_cached_online_master_list()
            stats_on = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in all_students_on}
            for ws in online_tabs:
                absentees = ws.get_all_records()
                for a in absentees:
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats_on:
                        stats_on[rid]["Absent"] += 1
            results_on = []
            for reg_id, data in stats_on.items():
                absent = data["Absent"]
                present = total_on_classes - absent
                percent = (present / total_on_classes) * 100 if total_on_classes else 0
                results_on.append((data["Name"], reg_id, present, absent, percent))
            results_on.sort(key=lambda x: (-x[4], -x[2]))
            on_msg = f"🏆 Online Top Performers (out of {total_on_classes} classes):\n\n"
            rank = 1
            prev_percent = None
            for name, reg, present, absent, percent in results_on:
                if prev_percent is None or percent < prev_percent:
                    if rank > 3:
                        break
                    prev_percent = percent
                on_msg += f"{rank}. {name} ({reg}) - ✅ {present}, ❌ {absent}, 📊 {percent:.1f}%\n"
                rank += 1

        safe_reply(message, off_msg + "\n\n" + on_msg)
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e) “
