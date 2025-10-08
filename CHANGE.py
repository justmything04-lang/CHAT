def find_student_by_reg(sheet, reg_id):
    try:
        rows = sheet.get_all_records()
        for r in rows:
            if str(r.get("Reg ID", "")).strip() == str(reg_id):
                return r
    except Exception as e:
        print("find_student_by_reg error:", e)
    return None

def get_user_mode(uid):
    reg_id = str(uid)
    # If in online master -> online
    if online_master_sheet:
        r = find_student_by_reg(online_master_sheet, reg_id)
        if r:
            return "online"
    # Else if in offline master -> offline
    r = find_student_by_reg(master_sheet, reg_id)
    if r:
        return "offline"
    return None

# ---------------- Telegram handlers / state ----------------
user_pending = {}
pending_change = {}
pending_time_change = {}
registration_pending = {}
