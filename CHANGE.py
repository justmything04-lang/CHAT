if mode == "online":
    today = get_today_date()
    timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

    # Match Reg ID against OnlineMasterList (which has numeric Reg IDs)
    students = get_cached_online_master_list()
    student = next((s for s in students if str(s.get("Reg ID", "")).strip() == str(reg_id).strip()), None)

    if not student:
        safe_reply(msg, "❌ Invalid RegID. You are not in the Online Master List.")
        return

    student_name = student.get("Name", "Unknown")
    row = [student_name, reg_id, today, easter, timestamp, str(msg.from_user.id)]

    with _queue_lock:
        write_queue.append(("online", row))
        marked_today_online_ids.add(str(msg.from_user.id))

    invalidate_cache("online_attendance_rows")
    safe_reply(msg, f"✅ Online attendance queued for {student_name} ({reg_id}) at {timestamp}")
