# Handle EasterEgg + RegID (works for both modes)
@bot.message_handler(func=lambda m:
    m.text is not None
    and not m.text.startswith('/')
    and str(m.from_user.id) not in pending_change   # <-- prevents hijacking "change egg"
    and str(m.from_user.id) not in pending_time_change  # <-- prevents hijacking "change time"
    )
