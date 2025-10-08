# Keyboards
def get_student_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("📝 Register"))
    kb.row(types.KeyboardButton("📍 Mark Attendance"))
    return kb

def get_teacher_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Top 3", "📅 EOD Report")
    kb.row("✏️ Change Egg", "🕒 Change Time")
    kb.row("🔄 Refresh Attendance")
    return kb

def get_location_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("Send Location 📍", request_location=True))
    return kb
