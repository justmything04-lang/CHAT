@bot.message_handler(content_types=['location'])
def handle_location(msg):
    try:
        reset_attendance_if_new_day()
        uid = msg.from_user.id

        # Verify user is offline in MasterList
        mode = get_user_mode(uid)
        if mode != "offline":
            safe_reply(msg, "⚠️ You are not registered as Offline.\nTap **📝 Register** and choose Offline.")
            return

        allowed = within_allowed_time()
        ok, txt = (allowed if isinstance(allowed, tuple) else (allowed, ""))
        if not ok:
            safe_reply(msg, txt or "⏰ Attendance not allowed right now.")
            return

        reg_id = str(uid)  # Reg ID == Telegram ID
        user_lat = msg.location.latitude
        user_lon = msg.location.longitude
        dist = distance_m(user_lat, user_lon, CLASS_LAT, CLASS_LON)
        if dist > RADIUS_METERS:
            safe_reply(msg, f"📍 Too far from class ({dist:.1f}m > {RADIUS_METERS}m).")
            return

        if str(uid) in marked_today_ids:
            safe_reply(msg, "⚠️ You’ve already marked attendance today (offline).")
            return

        # Validate in offline MasterList
        student = find_student_by_reg(master_sheet, reg_id)
        if not student:
            safe_reply(msg, "❌ You are not in the Offline Master List. Tap **📝 Register**.")
            return

        student_name = student.get("Name", f"Student_{reg_id}")
        timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        egg_placeholder = "-"
        row = [student_name, reg_id, get_today_date(), egg_placeholder, timestamp, str(uid)]
        with _queue_lock:
            write_queue.append(("offline", row))
            marked_today_ids.add(str(uid))
        invalidate_cache("attendance_rows")
        safe_reply(msg, f"✅ Offline attendance queued for {student_name} ({reg_id}) at {timestamp}")
    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("Location handler error:", e)
