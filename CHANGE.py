# ---------------- /top3 (offline + online, grouped style) ----------------
@bot.message_handler(commands=['top3'])
def send_top3(message):
    if str(message.from_user.id) != str(TEACHER_ID):
        safe_reply(message, "❌ Unauthorized.")
        return
    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            if total_classes == 0:
                return f"⚠️ No {label.lower()} attendance history yet."

            # Build stats
            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in tabs:
                absentees = ws.get_all_records()
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

            # Group into Top1, Top2, Top3
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
                        # Flush previous group
                        msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                        for g in group:
                            msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                        msg += "\n"
                        group = []
                    prev_percent = percent
                    rank += 1
                group.append((name, reg, present, absent, percent))

            # Flush last group (Top3)
            if group and rank-1 <= 3:
                msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                for g in group:
                    msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                msg += "\n"

            return msg.strip()

        # ----- OFFLINE -----
        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        offline_msg = build_top3(offline_tabs, get_cached_master_list(), len(offline_tabs), "Offline")

        # ----- ONLINE -----
        online_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-online")]
        online_msg = build_top3(online_tabs, get_cached_online_master_list(), len(online_tabs), "Online")

        safe_reply(message, offline_msg + "\n\n" + online_msg)

    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)
