# ---------------- Teacher buttons (fixed) ----------------
def _must_be_teacher(m):
    return str(m.from_user.id) == str(TEACHER_ID) or (ADMIN_ID and str(m.from_user.id) == str(ADMIN_ID))

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📊 Top 3")
def btn_top3(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    send_top3(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 EOD Report")
def btn_eod(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    send_report(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "🔄 Refresh Attendance")
def btn_refresh(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_refresh(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "🕒 Change Time")
def btn_change_time(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    safe_reply(m, "🕒 Please send the new Start Time (HH:MM):")
    pending_time_change[str(m.from_user.id)] = {"stage": "start"}

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 Bi-Weekly Report")
def btn_biweekly(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_biweekly(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📅 Monthly Report")
def btn_monthly(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_monthly(m)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text == "📘 Course Summary")
def btn_course(m):
    if not _must_be_teacher(m): 
        return safe_reply(m, "❌ Unauthorized.")
    manual_course_summary(m)
