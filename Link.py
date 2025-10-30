# ---------------- Teacher button handler ----------------
@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text in [
    "📊 Top 3", "📅 EOD Report", "🔄 Refresh Attendance", "🕒 Change Time"
])
@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text == "📅 Bi-Weekly Report")
def handle_biweekly_button(msg):
    manual_biweekly(msg)  # just reuse the command handler

@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text == "📅 Monthly Report")
def handle_monthly_button(msg):
    manual_monthly(msg)

@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text == "📘 Course Summary")
def handle_course_button(msg):
    manual_course_summary(msg)

def handle_teacher_buttons(msg):
    uid = str(msg.from_user.id)
    text = msg.text

    if uid != str(TEACHER_ID):
        safe_reply(msg, "❌ You are not authorized for this command.")
        return

    if text == "📊 Top 3":
        send_top3(msg)
    elif text == "📅 EOD Report":
        send_report(msg)
    elif text == "🔄 Refresh Attendance":
        manual_refresh(msg)
    elif text == "🕒 Change Time":
        safe_reply(msg, "🕒 Please send the new Start Time (HH:MM):")
        pending_time_change[uid] = {"stage": "start"}

# ----- Registration core -----
def upsert_student(sheet, reg_id, name, username):
    try:
        rows = sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("Reg ID","")).strip() == str(reg_id):
                # Update name if different
                if sheet.cell(i, 1).value != name:
                    sheet.update_cell(i, 1, name)
                return "updated"
        # Append new
        sheet.append_row([name, str(reg_id)], value_input_option='USER_ENTERED')
        return "inserted"
    except Exception as e:
        print("upsert_student error:", e)
        return "error"
