def publish_top3_to_teacher_and_topic():
    """
    Run the Top3 logic without depending on a Telegram message object.
    Sends combined Top3 to TEACHER_ID (DM) and posts to the public topic.
    """
    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            if total_classes == 0:
                return f"⚠️ No {label.lower()} attendance history yet."

            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in tabs:
                absentees = _gs_read(lambda: ws.get_all_records())
                for a in absentees:
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1

            results = []
            for reg_id, data in stats.items():
                absent = data["Absent"]
                present = total_classes - absent
                percent = (present / total_classes) * 100 if total_classes else 0
                results.append((data["Name"], reg_id, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))

            msg = f"🏆 {label} Top Performers (out of {total_classes} classes):\n\n"
            rank = 1
            prev_percent = None
            group = []
            rank_emojis = {1: "🥇 Top 1", 2: "🥈 Top 2", 3: "🥉 Top 3"}
            for name, reg, present, absent, percent in results:
                if prev_percent is None or percent < prev_percent:
                    if rank > 3:
                        break
                    if group:
                        msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                        for g in group:
                            msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                        msg += "\n"
                        group = []
                    prev_percent = percent
                    rank += 1
                group.append((name, reg, present, absent, percent))

            if group and rank-1 <= 3:
                msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                for g in group:
                    msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                msg += "\n"

            return msg.strip()

        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        offline_msg = build_top3(offline_tabs, get_cached_master_list(), len(offline_tabs), "Offline")

        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        online_msg = build_top3(online_tabs, get_cached_online_master_list(), len(online_tabs), "Online")

        combined = offline_msg + "\n\n" + online_msg

        
for student in top3_students:
    msg_s = APP_STUDENT_TOP3.format(
        student_name=student.name,
        period_type="Top-3",
        range_or_course="Current Window"
    )
    msg_p = APP_PARENT_TOP3.format(
        student_name=student.name,
        period_type="Top-3",
        range_or_course="Current Window"
    )
    await send_dm(student.telegram_id, msg_s)
    if student.parent_id:
        await send_dm(student.parent_id, msg_p)
    db.update_streak(student.id, boost=True
