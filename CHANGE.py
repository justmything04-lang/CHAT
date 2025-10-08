# ----- Registration -----
def upsert_student(sheet, reg_id, name, username):
    """Insert or update student in given sheet using Reg ID as key."""
    try:
        rows = sheet.get_all_records()
        # Check if exists by Reg ID
        for i, r in enumerate(rows, start=2):  # header is row 1
            if str(r.get("Reg ID", "")).strip() == str(reg_id):
                # Update name/username if you keep those columns; minimal: update Name only
                try:
                    sheet.update_acell(f"A{i}", name)  # Name column
                except:
                    pass
                return "updated"
        # Append if not exists; sheet expects at least Name & Reg ID
        sheet.append_row([name, str(reg_id)], value_input_option='USER_ENTERED')
        return "inserted"
    except Exception as e:
        print("upsert_student error:", e)
        return "error"

@bot.message_handler(func=lambda m: m.text == "📝 Register")
def register_init(msg):
    uid = msg.from_user.id
    registration_pending[uid] = True
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("🧑‍🏫 Offline"), types.KeyboardButton("💻 Online"))
    safe_reply(msg, "Choose your mode once:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🧑‍🏫 Offline", "💻 Online"])
def register_choose_mode(msg):
    uid = msg.from_user.id
    if uid not in registration_pending:
        # Not in registration flow; ignore
        return

    mode = "offline" if msg.text == "🧑‍🏫 Offline" else "online"
    name = (msg.from_user.first_name or "").strip() or f"Student_{uid}"
    username = (msg.from_user.username or "").strip()
    reg_id = str(uid)  # Reg ID == Telegram ID

    if mode == "offline":
        # Write into MasterList
        status = upsert_student(master_sheet, reg_id, name, username)
    else:
        # Write into OnlineMasterList
        if online_master_sheet is None:
            safe_reply(msg, "⚠️ Online MasterList sheet is not available. Ask admin to create 'OnlineMasterList' tab.")
            registration_pending.pop(uid, None)
            return
        status = upsert_student(online_master_sheet, reg_id, name, username)

    registration_pending.pop(uid, None)
    kb = get_student_keyboard()
    safe_reply(msg, f"✅ Registered as **{mode.title()}**.\nYour RegID = Telegram ID `{reg_id}`.\nNow tap **📍 Mark Attendance** daily.", reply_markup=kb)
