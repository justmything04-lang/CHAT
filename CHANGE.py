# ---------------- Sheets (offline + online) ----------------
attendance_sheet = client.open_by_key(SHEET_ID).worksheet("Attendance")
master_sheet = client.open_by_key(SHEET_ID).worksheet("MasterList")
settings_sheet = client.open_by_key(SHEET_ID).worksheet("Settings")

# Online tabs (same workbook, just different tabs)
try:
    online_attendance_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineAttendance")
    online_master_sheet = client.open_by_key(SHEET_ID).worksheet("OnlineMasterList")
except Exception as e:
    print("⚠️ Online sheets access error (check tab names in Google Sheet):", e)
    online_attendance_sheet = None
    online_master_sheet = None
