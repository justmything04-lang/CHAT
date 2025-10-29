# build_demo_reports.py
# Creates demo Excel workbooks & charts that mirror your bot’s Sheets structure.

import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---------- Config (tweak as you like) ----------
OUT_DIR = "out"
N_OFFLINE = 30      # offline students
N_ONLINE  = 20      # online students
P_PRESENT_OFF = 0.85
P_PRESENT_ON  = 0.78
WINDOW_DAYS = 14     # for bi-weekly summary
COURSE_DAYS = 90     # for course summary

# ---------- Helpers ----------
TODAY = datetime.now().date()
START_MONTH = TODAY.replace(day=1)
END_MONTH = (START_MONTH + pd.offsets.MonthEnd(0)).date()

np.random.seed(7)

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def make_students(n, start_id=1000):
    names = [f"Student_{i}" for i in range(start_id, start_id + n)]
    reg_ids = [str(10_000_000 + i) for i in range(n)]
    usernames = [f"user_{i}" for i in range(n)]
    phones = [f"+91{np.random.randint(6000000000, 9999999999)}" for _ in range(n)]
    return pd.DataFrame({
        "Name": names,
        "Reg ID": reg_ids,
        "Username": usernames,
        "ParentPhone": phones,
        "ParentChatId": ["" for _ in range(n)],
        "ParentLinked": ["No" for _ in range(n)],
        "ParentInvited": ["No" for _ in range(n)]
    })

def mark_attendance(df_master, start_date, end_date, p_present=0.82):
    days = pd.date_range(start_date, end_date, freq="D")
    rows = []
    for day in days:
        for _, r in df_master.iterrows():
            if np.random.rand() < p_present:
                rows.append([r["Name"], r["Reg ID"], str(day.date()), "-", str(day)[:19], r["Reg ID"]])
    cols = ["Name","Reg ID","Date","EasterEgg","Timestamp","Telegram ID"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def absentees_for_day(df_master, attendance_df, day_str):
    present_ids = set(attendance_df.query("Date == @day_str")["Reg ID"].astype(str))
    all_ids = set(df_master["Reg ID"].astype(str))
    abs_ids = [rid for rid in all_ids if rid not in present_ids]
    out = df_master.set_index("Reg ID").loc[abs_ids, ["Name"]].reset_index()
    out["Date"] = day_str
    return out[["Name","Reg ID","Date"]]

def band_from_pct(p):
    if p >= 1.0: return "100%"
    if p >= 0.8: return "High"
    if p >= 0.6: return "Average"
    return "Low"

def summarize_window(df_off, df_on, att_off, att_on, start_date, end_date):
    students = []
    all_days = pd.date_range(start_date, end_date, freq="D")
    classes_window = len(all_days)
    att_all = pd.concat([att_off, att_on], ignore_index=True)
    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"])
            name = r["Name"]
            pres = att_all.query("`Reg ID` == @rid and Date >= @str(start_date) and Date <= @str(end_date)")
            present_days = pres["Date"].nunique()
            abs_days = classes_window - present_days
            pct = present_days / classes_window if classes_window else 0
            students.append([rid, name, mode, classes_window, present_days, abs_days, pct, band_from_pct(pct)])
    cols = ["Reg ID","Name","Mode","Classes_Window","Presents_Window","Absents_Window","Attendance%_Window","Band"]
    return pd.DataFrame(students, columns=cols)

def summarize_month(df_off, df_on, att_off, att_on, month_start, month_end):
    students = []
    att_all = pd.concat([att_off, att_on], ignore_index=True)
    all_days = pd.date_range(month_start, month_end, freq="D")
    classes_month = len(all_days)
    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"]); name = r["Name"]
            pres = att_all.query("`Reg ID` == @rid and Date >= @str(month_start) and Date <= @str(month_end)")
            present_days = pres["Date"].nunique()
            abs_days = classes_month - present_days
            pct = present_days / classes_month if classes_month else 0
            students.append([rid, name, mode, classes_month, present_days, abs_days, pct, band_from_pct(pct)])
    cols = ["Reg ID","Name","Mode","Classes_Month","Presents_Month","Absents_Month","Attendance%_Month","Band_Month"]
    return pd.DataFrame(students, columns=cols)

def summarize_course(df_off, df_on, att_off, att_on, start_date, end_date):
    students = []
    att_all = pd.concat([att_off, att_on], ignore_index=True)
    all_days = pd.date_range(start_date, end_date, freq="D")
    classes_total = len(all_days)
    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"]); name = r["Name"]
            pres = att_all.query("`Reg ID` == @rid and Date >= @str(start_date) and Date <= @str(end_date)")
            present_days = pres["Date"].nunique()
            abs_days = classes_total - present_days
            pct = present_days / classes_total if classes_total else 0
            students.append([rid, name, mode, classes_total, present_days, abs_days, pct, band_from_pct(pct)])
    cols = ["Reg ID","Name","Mode","Classes_Total","Presents_Total","Absents_Total","Attendance%_Total","Band_Total"]
    return pd.DataFrame(students, columns=cols)

def chart_band_distribution(df, band_col, title, out_path):
    counts = df[band_col].value_counts().reindex(["100%","High","Average","Low"]).fillna(0)
    plt.figure()
    counts.plot(kind="bar")  # NOTE: no custom colors/styles per your rules
    plt.title(title)
    plt.xlabel("Band")
    plt.ylabel("Students")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

def save_xlsx(path, frames_by_sheet):
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        for sheet, frame in frames_by_sheet.items():
            frame.to_excel(xw, sheet_name=sheet, index=False)

# ---------- Build demo data ----------
ensure_dir(OUT_DIR)

df_master_off = make_students(N_OFFLINE, start_id=2000)
df_master_on  = make_students(N_ONLINE,  start_id=3000)

start_14 = TODAY - timedelta(days=WINDOW_DAYS-1)
att_off = mark_attendance(df_master_off, start_14, TODAY, p_present=P_PRESENT_OFF)
att_on  = mark_attendance(df_master_on,  start_14, TODAY, p_present=P_PRESENT_ON)

absent_off_today = absentees_for_day(df_master_off, att_off, str(TODAY))
absent_on_today  = absentees_for_day(df_master_on,  att_on,  str(TODAY))

settings_tab = pd.DataFrame([{"DailyEasterEgg":"🙂","StartTime":"09:00","EndTime":"13:00"}])
parent_queue_tab = pd.DataFrame(columns=["RegID","Date","Mode","Message","Status","CreatedAt","SentAt","Attempts"])

biweekly_df = summarize_window(df_master_off, df_master_on, att_off, att_on, start_14, TODAY)
monthly_df  = summarize_month(df_master_off, df_master_on, att_off, att_on, START_MONTH, END_MONTH)
course_start = TODAY - timedelta(days=COURSE_DAYS-1)
course_df   = summarize_course(df_master_off, df_master_on, att_off, att_on, course_start, TODAY)

# ---------- Save: Main workbook (all tabs) ----------
save_xlsx(
    os.path.join(OUT_DIR, "main_workbook.xlsx"),
    {
        "MasterList": df_master_off,
        "OnlineMasterList": df_master_on,
        "Attendance": att_off,
        "OnlineAttendance": att_on,
        "Settings": settings_tab,
        "ParentQueue": parent_queue_tab,
        "BiWeekly_Summary": biweekly_df,
        "Monthly_Summary": monthly_df,
        "Course_Summary": course_df,
    }
)

# ---------- Save: Absentee workbooks (today) ----------
save_xlsx(
    os.path.join(OUT_DIR, "offline_absentees_demo.xlsx"),
    { f"{TODAY}-offline": absent_off_today }
)
save_xlsx(
    os.path.join(OUT_DIR, "online_absentees_demo.xlsx"),
    { f"{TODAY}-online":  absent_on_today }
)

# ---------- Save: Standalone summary files ----------
biweekly_path = os.path.join(OUT_DIR, "biweekly_summary.xlsx")
monthly_path  = os.path.join(OUT_DIR, "monthly_summary.xlsx")
course_path   = os.path.join(OUT_DIR, "course_summary.xlsx")
biweekly_df.to_excel(biweekly_path, index=False)
monthly_df.to_excel(monthly_path, index=False)
course_df.to_excel(course_path, index=False)

# ---------- Charts ----------
chart_band_distribution(biweekly_df, "Band",        "Bi-Weekly Band Distribution",  os.path.join(OUT_DIR, "biweekly_band_distribution.png"))
chart_band_distribution(monthly_df,  "Band_Month",  "Monthly Band Distribution",    os.path.join(OUT_DIR, "monthly_band_distribution.png"))
chart_band_distribution(course_df,   "Band_Total",  "Course Band Distribution",     os.path.join(OUT_DIR, "course_band_distribution.png"))

print("\nAll files generated in:", os.path.abspath(OUT_DIR))
