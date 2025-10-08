@bot.message_handler(func=lambda msg: isinstance(msg.text, str) and msg.text in [
    "📍 Mark Attendance", "📊 Top 3", "✏️ Change Egg",
    "🕒 Change Time", "📅 EOD Report", "🔄 Refresh Attendance"
])
