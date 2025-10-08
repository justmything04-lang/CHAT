# ---------------- Telegram handlers / state ----------------
user_pending = {}         # telegram_id -> {"mode": "offline"/"online", "reg_id": "..."}
pending_change = {}       # for teacher change egg
pending_time_change = {}

# Registration state
registration_pending = {}  # telegram_id -> True (waiting to choose mode)
