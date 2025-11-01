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




def publish_top3_to_teacher_and_topic():
    """
    Run the Top3 logic without depending on a Telegram message object.
    Sends combined Top3 to TEACHER_ID (DM) and posts to the public topic.
    Also sends appreciation messages to Top-3 students and their parents (if linked).
    """
    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            """
            Returns: (msg_str, top_reg_list)
            - msg_str: formatted message text for this mode
            - top_reg_list: list of Reg IDs (strings) for top performers (up to 3)
            """
            if total_classes == 0:
                return (f"⚠️ No {label.lower()} attendance history yet.", [])

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
            # sort by percent desc, then present desc
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

            # determine top_reg_list: first up to 3 unique reg ids from the sorted results
            top_regs = []
            for _, reg, _, _, _ in results:
                if reg not in top_regs:
                    top_regs.append(reg)
                if len(top_regs) >= 3:
                    break

            return msg.strip(), top_regs

        # build offline & online parts
        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        offline_msg, offline_top = build_top3(offline_tabs, get_cached_master_list(), len(offline_tabs), "Offline")

        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        online_msg, online_top = build_top3(online_tabs, get_cached_online_master_list(), len(online_tabs), "Online")

        combined = offline_msg + "\n\n" + online_msg

        # --- Send appreciation messages to Top performers (unique + preserve order) ---
        top_ordered = list(dict.fromkeys(offline_top + online_top))  # unique preserving order
        for reg in top_ordered:
            try:
                # find the student's display name from cached lists
                student_rec = None
                for r in get_cached_master_list():
                    if str(r.get("Reg ID","")).strip() == str(reg).strip():
                        student_rec = r
                        break
                if not student_rec:
                    for r in get_cached_online_master_list():
                        if str(r.get("Reg ID","")).strip() == str(reg).strip():
                            student_rec = r
                            break
                student_name = student_rec.get("Name","") if student_rec else ""

                # student DM (Reg ID is Telegram ID)
                try:
                    safe_send_chat(int(str(reg).strip()), APP_STUDENT_TOP3.format(
                        student_name=student_name or str(reg),
                        period_type="Top-3",
                        range_or_course="Current Window"
                    ))
                except Exception:
                    # fallback: try string id (some systems store without casting)
                    try:
                        safe_send_chat(str(reg).strip(), APP_STUDENT_TOP3.format(
                            student_name=student_name or str(reg),
                            period_type="Top-3",
                            range_or_course="Current Window"
                        ))
                    except Exception:
                        pass

                # parent DM (if linked)
                try:
                    sheet, mode = find_sheet_for_reg(reg)
                    if sheet:
                        info = get_parent_info(sheet, reg)
                        parent_chat = info.get("ParentChatId","").strip()
                        if parent_chat:
                            try:
                                safe_send_chat(int(parent_chat), APP_PARENT_TOP3.format(
                                    student_name=student_name or str(reg),
                                    period_type="Top-3",
                                    range_or_course="Current Window"
                                ))
                            except Exception:
                                try:
                                    safe_send_chat(parent_chat, APP_PARENT_TOP3.format(
                                        student_name=student_name or str(reg),
                                        period_type="Top-3",
                                        range_or_course="Current Window"
                                    ))
                                except Exception:
                                    pass
                except Exception:
                    pass

                # optional streak boost (call your helper if present)
                try:
                    update_streak(reg, boost=True)
                except Exception:
                    try:
                        db.update_streak(reg, boost=True)
                    except Exception:
                        pass

            except Exception as e:
                print("⚠️ Top-3 appreciation send error for", reg, ":", e)

        # send combined Top3 to teacher + public topic
        if TEACHER_ID:
            try:
                safe_send_chat(TEACHER_ID, combined)
            except Exception:
                pass
        _post_public(combined)
        print("✅ Auto Top3 published (teacher + topic).")

    except Exception as e:
        print("publish_top3_to_teacher_and_topic error:", e)












==> Running 'python 11111.py'
  File "/opt/render/project/src/11111.py", line 2242
    for student in get_cached_master_list():
IndentationError: unexpected indent
==> Exited with status 1

    # Deny live/backup in Academy app for Low band
    _enforce_low_in_app(low_ids, win_start, win_end)

    print("✅ Bi-Weekly: topic posted, admin notified, sheet updated, parents cautioned, app lock attempted.")

      for student in get_cached_master_list():
        msg_s = APP_STUDENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        msg_p = APP_PARENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        safe_send_chat(student["Reg ID"], msg_s)
        if student.get("ParentChatId"):
            safe_send_chat(student["ParentChatId"], msg_p)
        db.update_streak(student["Reg ID"], boost=True)

