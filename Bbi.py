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














# ---------------- Background workers ----------------

def _is_eod_done_for(today_str):
    """Returns True if today's offline+online absentee tabs already exist."""
    try:
        off_file = client.open_by_key(ABSENTEE_SHEET_ID)
        on_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        off_done = any(ws.title == f"{today_str}-offline" for ws in off_file.worksheets())
        on_done = any(ws.title == f"{today_str}-online" for ws in on_file.worksheets())
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
            today = get_today_date()

            # build today's localized end time
            try:
                end_dt = datetime.strptime(today + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = datetime.now(ZoneInfo(TIMEZONE))

            pre_trigger_dt = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)
            now_local = datetime.now(ZoneInfo(TIMEZONE))

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
            today = now_local.date()

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
            end_str = s.get("EndTime", "23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt = end_dt - timedelta(minutes=5)
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
            today = now_local.date()

            start = _get_class_start_date()
            # compute 30-day windows:
            days = _days_since(start, today)
            if days < 0:
                time.sleep(120)
                continue
            idx = days // 30
            win_start = start + timedelta(days=30 * idx)
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
            end_str = s.get("EndTime", "23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt = end_dt - timedelta(minutes=5)
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
                time.sleep(3600 * 6)  # sleep 6h if none
                continue

            # For each pending, if parent linked now -> send
            for row_idx, r in pending:
                reg_id = str(r.get("RegID", "")).strip()
                sheet, mode = find_sheet_for_reg(reg_id)
                info = get_parent_info(sheet, reg_id) if sheet else {}
                chatid = info.get("ParentChatId", "").strip()
                linked = info.get("ParentLinked", "").strip().lower() == "yes"
                if chatid and linked:
                    try:
                        safe_send_chat(chatid, r.get("Message", ""))
                        parentqueue_mark_sent(row_idx)
                    except Exception as e:
                        print("parent_queue_retry send error:", e)
                        parentqueue_bump_attempt(row_idx)
                else:
                    parentqueue_bump_attempt(row_idx)

            time.sleep(3600 * 24)  # 24 hours
        except Exception as e:
            print("parent_queue_retry_worker error:", e)
            time.sleep(3600 * 6)


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
                    off_linked = sum(1 for r in off_list if str(r.get("ParentChatId", "")).strip())
                    on_linked = sum(1 for r in on_list if str(r.get("ParentChatId", "")).strip())

                    msg = TPL_FACULTY_WEEKLY.format(
                        off_linked=off_linked,
                        off_total=off_total,
                        on_linked=on_linked,
                        on_total=on_total,
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


def daily_motivation_worker():
    """
    Runs once per day, sends DAILY_MSG to all students via safe_send_chat.
    Uses master/online master lists and updates streak via db.update_streak(student_id, daily=True).
    """
    while True:
        try:
            now = datetime.now(ZoneInfo(TIMEZONE))
            # Run at 20:00 local if minute==0 window (small window to avoid exact schedule dependency)
            if now.hour == 20 and 0 <= now.minute < 2:
                today_str = now.strftime("%b %d, %Y")
                # offline students
                for s in get_cached_master_list():
                    try:
                        chatid = str(s.get("Reg ID", "")).strip()
                        attendance_pct = s.get("AttendancePct", "") or ""  # optional field if you maintain it
                        group_name = s.get("Group", "")
                        msg = DAILY_MSG.format(
                            student_name=s.get("Name", ""),
                            attendance_pct=attendance_pct,
                            group_name=group_name,
                            date=today_str,
                        )
                        safe_send_chat(chatid, msg)
                        try:
                            db.update_streak(chatid, daily=True)
                        except Exception:
                            pass
                    except Exception:
                        pass
                # online students
                for s in get_cached_online_master_list():
                    try:
                        chatid = str(s.get("Reg ID", "")).strip()
                        attendance_pct = s.get("AttendancePct", "") or ""
                        group_name = s.get("Group", "")
                        msg = DAILY_MSG.format(
                            student_name=s.get("Name", ""),
                            attendance_pct=attendance_pct,
                            group_name=group_name,
                            date=today_str,
                        )
                        safe_send_chat(chatid, msg)
                        try:
                            db.update_streak(chatid, daily=True)
                        except Exception:
                            pass
                    except Exception:
                        pass
                # sleep a minute so we don't double-run within window
                time.sleep(60)
            time.sleep(20)
        except Exception as e:
            print("daily_motivation_worker error:", e)
            time.sleep(60)


# start background threads (after all worker functions are defined)
threading.Thread(target=auto_eod_worker, daemon=True).start()
threading.Thread(target=parent_queue_retry_worker, daemon=True).start()
threading.Thread(target=weekly_summary_worker, daemon=True).start()
threading.Thread(target=biweekly_worker, daemon=True).start()
threading.Thread(target=monthly_worker, daemon=True).start()
threading.Thread(target=daily_motivation_worker, daemon=True).start()
