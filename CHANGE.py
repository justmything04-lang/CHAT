# Handle EasterEgg + RegID (works for both modes)
@bot.message_handler(func=lambda m:
    m.text is not None
    and not m.text.startswith('/')
    and str(m.from_user.id) not in pending_change   # 🚀 prevents conflict with egg change
    and str(m.from_user.id) not in pending_time_change  # 🚀 prevents conflict with time change
)
def handle_easteregg(msg):
    try:
        reset_attendance_if_new_day()
        text = msg.text.strip()
        parts = text.split()
        if len(parts) != 2:
            safe_reply(msg, "❌ Invalid format. Use `<EasterEgg> <RegID>`")
            return

        easter, reg_id = parts
        daily_egg, _, _ = get_settings()
        allowed = within_allowed_time()
        if isinstance(allowed, tuple):
            ok, msg_text = allowed
        else:
            ok, msg_text = allowed, ""
        if not ok:
            safe_reply(msg, msg_text)
            return

        if easter.lower() != daily_egg.lower():
            safe_reply(msg, "❌ Wrong Easter Egg.")
            return

        # Determine mode (previous selection or default offline)
        pending = user_pending.get(msg.from_user.id) or {}
        mode = pending.get("mode", "offline")

        if mode == "online":
            today = get_today_date()
            timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

            # Match Reg ID against OnlineMasterList
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

        else:
            # For offline, store reg_id and wait for location
            user_pending[msg.from_user.id] = {"mode": "offline", "reg_id": reg_id}
            safe_reply(msg, "✅ Verified — now share 📍 location for offline attendance.")

    except Exception as e:
        safe_reply(msg, f"⚠️ Error: {e}")
        print("EasterEgg handler error:", e)
