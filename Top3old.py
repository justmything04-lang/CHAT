# ---------------- /top3 (offline + online) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        # --- OFFLINE ---
        offline_file = client.open_by_key(ABSENTEE_SHEET_ID)
        offline_tabs = [ws for ws in offline_file.worksheets() if ws.title.endswith("-offline")]
        total_off = len(offline_tabs)
        if total_off == 0:
            off_msg = "⚠️ No offline attendance history yet."
        else:
            students = get_cached_master_list()
            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in offline_tabs:
                for a in ws.get_all_records():
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1
            results = []
            for rid, data in stats.items():
                absent = data["Absent"]
                present = total_off - absent
                percent = (present / total_off) * 100 if total_off else 0
                results.append((data["Name"], rid, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))
            off_msg = f"🏆 Offline Top Performers (out of {total_off} classes):\n\n"
            rank, prev_percent = 1, None
            for name, reg, pres, absn, pct in results:
                if prev_percent is None or pct < prev_percent:
                    if rank > 3: break
                    prev_percent = pct
                off_msg += f"{rank}. {name} ({reg}) - ✅ {pres}, ❌ {absn}, 📊 {pct:.1f}%\n"
                rank += 1

        # --- ONLINE ---
        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        total_on = len(online_tabs)
        if total_on == 0:
            on_msg = "⚠️ No online attendance history yet."
        else:
            students_on = get_cached_online_master_list()
            stats_on = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students_on}
            for ws in online_tabs:
                for a in ws.get_all_records():
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats_on:
                        stats_on[rid]["Absent"] += 1
            results_on = []
            for rid, data in stats_on.items():
                absent = data["Absent"]
                present = total_on - absent
                percent = (present / total_on) * 100 if total_on else 0
                results_on.append((data["Name"], rid, present, absent, percent))
            results_on.sort(key=lambda x: (-x[4], -x[2]))
            on_msg = f"🏆 Online Top Performers (out of {total_on} classes):\n\n"
            rank, prev_percent = 1, None
            for name, reg, pres, absn, pct in results_on:
                if prev_percent is None or pct < prev_percent:
                    if rank > 3: break
                    prev_percent = pct
                on_msg += f"{rank}. {name} ({reg}) - ✅ {pres}, ❌ {absn}, 📊 {pct:.1f}%\n"
                rank += 1

        safe_reply(message, off_msg + "\n\n" + on_msg)
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)
