@bot.message_handler(func=lambda m: m.text == "📍 Mark Attendance")
def mark_attendance_button(msg):
    uid = msg.from_user.id
    mode = get_user_mode(uid)
    if mode is None:
        safe_reply(msg, "⚠️ You are not registered.\nTap **📝 Register** first.", reply_markup=get_student_keyboard())
        return

    allowed = within_allowed_time()
    ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
    if not ok:
        safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
        return

    if mode == "online":
        # Direct mark
        reg_id = str(uid)
        student = find_student_by_reg(online_master_sheet, reg_id) if online_master_sheet else None
        student_name = (student or {}).get("Name", f"Student_{reg_id}")

        today = get_today_date()
        timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        egg_placeholder = "-"  # EasterEgg no longer used
        row = [student_name, reg_id, today, egg_placeholder, timestamp, str(uid)]

        if str(uid) in marked_today_online_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today (online).")
            return

        with _queue_lock:
            write_queue.append(("online", row))
            marked_today_online_ids.add(str(uid))
        invalidate_cache("online_attendance_rows")
        safe_reply(msg, f"✅ Online attendance queued for {student_name} ({reg_id}) at {timestamp}")

    else:
        # Offline: ask for location
        safe_reply(msg, "📍 Send your current location to complete offline attendance.", reply_markup=get_location_keyboard())
