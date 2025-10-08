# ---------------- Sheets (offline + online) ----------------
attendance_sheet = client.open_by_key(SHEET_ID).worksheet("Attendance")
master_sheet = client.open_by_key(SHEET_ID).worksheet("MasterList")
settings_sheet = client.open_by_key(SHEET_ID).worksheet("Settings")

# Online tabs (may be in same workbook or another workbook)
try:
    online_wb = client.open_by_key(ONLINE_SHEET_ID)
    online_attendance_sheet = online_wb.worksheet(ONLINE_ATTENDANCE_TAB)
    online_master_sheet = online_wb.worksheet(ONLINE_MASTER_TAB)
except Exception as e:
    # If online tabs missing, print error but continue (you can create them manually)
    print("⚠️ Online sheets access error (check ONLINE_SHEET_ID / tab names):", e)
    online_attendance_sheet = None
    online_master_sheet = None
