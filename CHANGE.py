@bot.message_handler(commands=['start'])
def start_cmd(msg):
    uid = str(msg.from_user.id)
    if uid == str(TEACHER_ID):
        kb = get_teacher_keyboard()
        safe_reply(msg, "👋 Hello Sir! Your panel:", reply_markup=kb)
    else:
        kb = get_student_keyboard()
        safe_reply(
            msg,
            "👋 Welcome!\n\n"
            "• Tap **📝 Register** once (bot will auto-save your Telegram ID as RegID and your Username).\n"
            "• Choose **Offline** or **Online**.\n"
            "• Then every day just tap **📍 Mark Attendance**.\n\n"
            "Offline will ask for location; Online marks immediately.",
            reply_markup=kb
        )
