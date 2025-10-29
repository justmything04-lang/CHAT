# build_demo_reports.py
# Creates demo Excel workbooks & high-DPI charts that mirror your bot’s Google Sheets structure.

import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---------------- CONFIG (tweak freely) ----------------
OUT_DIR = "out"

# student counts
N_OFFLINE = 30
N_ONLINE  = 20

# attendance probabilities
P_PRESENT_OFF = 0.85
P_PRESENT_ON  = 0.78

# reporting windows
WINDOW_DAYS = 14     # for bi-weekly summary
COURSE_DAYS = 90     # for course summary (rolling back from today)

# random seed for reproducibility
np.random.seed(7)
random.seed(7)

# dates
TODAY = datetime.now().date()
START_MONTH = TODAY.replace(day=1)
END_MONTH = (START_MONTH + pd.offsets.MonthEnd(0)).date()  # last day of this month

# ---------------- Matplotlib (bigger, crisp charts) ----------------
plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 300,
    "font.size": 13,
    "axes.titlesize": 18,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12
})

# ---------------- Helpers ----------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def make_students(n: int, start_id: int = 1000) -> pd.DataFrame:
    """Create demo students with safe (random) Indian phone numbers."""
    first = ["Aarav","Ishaan","Diya","Meera","Rahul","Kiran","Maya","Anika","Rohan","Kabir",
             "Riya","Saanvi","Ayaan","Arjun","Veer","Dev","Ira","Advika","Vikram","Nikhil"]
    last  = ["K","R","S","M","B","T","N","P","L","G"]

    rows = []
    for i in range(n):
        reg_id = str(start_id + i)
        name = f"{random.choice(first)} {random.choice(last)}"
        # use Python's random for 64-bit safe range
        phone = f"+91{random.randint(6000000000, 9999999999)}"
        rows.append({
            "Name": name,
            "Reg ID": reg_id,
            "Username": f"user_{reg_id}",
            "ParentPhone": phone,
            "ParentChatId": "",
            "ParentLinked": "No",
            "ParentInvited": "No"
        })
    return pd.DataFrame(rows)

def mark_attendance(df_master: pd.DataFrame,
                    start_date: datetime.date,
                    end_date: datetime.date,
                    p_present: float = 0.82) -> pd.DataFrame:
    """Simulate daily attendance marks between start_date and end_date."""
    days = pd.date_range(start_date, end_date, freq="D")
    rows = []
    for day in days:
        for _, r in df_master.iterrows():
            if np.random.rand() < p_present:
                rows.append([
                    r["Name"],
                    r["Reg ID"],
                    str(day.date()),  # keep YYYY-MM-DD string for saving
                    "-",                               # EasterEgg placeholder
                    f"{str(day.date())} 09:{random.randint(10,59):02d}:00",  # Timestamp-ish
                    r["Reg ID"]                         # Telegram ID = Reg ID (demo)
                ])
    cols = ["Name","Reg ID","Date","EasterEgg","Timestamp","Telegram ID"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def absentees_for_day(df_master: pd.DataFrame, attendance_df: pd.DataFrame, day_str: str) -> pd.DataFrame:
    """Who is absent on a specific date (by Reg ID)?"""
    if attendance_df.empty:
        present_ids = set()
    else:
        present_ids = set(attendance_df[attendance_df["Date"] == day_str]["Reg ID"].astype(str))
    all_ids = set(df_master["Reg ID"].astype(str))
    abs_ids = sorted([rid for rid in all_ids if rid not in present_ids])
    if not abs_ids:
        return pd.DataFrame(columns=["Name","Reg ID","Date"])
    out = df_master.set_index("Reg ID").loc[abs_ids, ["Name"]].reset_index()
    out["Date"] = day_str
    return out[["Name","Reg ID","Date"]]

def band_from_pct(p: float) -> str:
    if p >= 1.0: return "100%"
    if p >= 0.8: return "High"
    if p >= 0.6: return "Average"
    return "Low"

def _prep_attendance_for_range(att_off: pd.DataFrame, att_on: pd.DataFrame) -> pd.DataFrame:
    """Concat and convert Date to datetime64[ns] for robust range filtering."""
    att_all = pd.concat([att_off, att_on], ignore_index=True)
    if not att_all.empty:
        att_all["Date"] = pd.to_datetime(att_all["Date"], format="%Y-%m-%d", errors="coerce")
    return att_all

def summarize_window(df_off: pd.DataFrame, df_on: pd.DataFrame,
                     att_off: pd.DataFrame, att_on: pd.DataFrame,
                     start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """Bi-weekly style (rolling) summary using boolean masks (no .query())."""
    students = []
    all_days = pd.date_range(start_date, end_date, freq="D")
    classes_window = len(all_days)

    att_all = _prep_attendance_for_range(att_off, att_on)
    start_ts = pd.Timestamp(start_date)
    end_ts   = pd.Timestamp(end_date)

    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"])
            name = r["Name"]
            if att_all.empty:
                present_days = 0
            else:
                mask = (att_all["Reg ID"].astype(str) == rid) & att_all["Date"].between(start_ts, end_ts)
                # count unique dates attended
                present_days = att_all.loc[mask, "Date"].dt.normalize().nunique()
            abs_days = classes_window - present_days
            pct = present_days / classes_window if classes_window else 0.0
            students.append([rid, name, mode, classes_window, present_days, abs_days, pct, band_from_pct(pct)])

    cols = ["Reg ID","Name","Mode","Classes_Window","Presents_Window","Absents_Window","Attendance%_Window","Band"]
    return pd.DataFrame(students, columns=cols)

def summarize_month(df_off: pd.DataFrame, df_on: pd.DataFrame,
                    att_off: pd.DataFrame, att_on: pd.DataFrame,
                    month_start: datetime.date, month_end: datetime.date) -> pd.DataFrame:
    students = []
    att_all = _prep_attendance_for_range(att_off, att_on)
    start_ts = pd.Timestamp(month_start)
    end_ts   = pd.Timestamp(month_end)

    all_days = pd.date_range(month_start, month_end, freq="D")
    classes_month = len(all_days)

    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"]); name = r["Name"]
            if att_all.empty:
                present_days = 0
            else:
                mask = (att_all["Reg ID"].astype(str) == rid) & att_all["Date"].between(start_ts, end_ts)
                present_days = att_all.loc[mask, "Date"].dt.normalize().nunique()
            abs_days = classes_month - present_days
            pct = present_days / classes_month if classes_month else 0.0
            students.append([rid, name, mode, classes_month, present_days, abs_days, pct, band_from_pct(pct)])

    cols = ["Reg ID","Name","Mode","Classes_Month","Presents_Month","Absents_Month","Attendance%_Month","Band_Month"]
    return pd.DataFrame(students, columns=cols)

def summarize_course(df_off: pd.DataFrame, df_on: pd.DataFrame,
                     att_off: pd.DataFrame, att_on: pd.DataFrame,
                     start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    students = []
    att_all = _prep_attendance_for_range(att_off, att_on)
    start_ts = pd.Timestamp(start_date)
    end_ts   = pd.Timestamp(end_date)

    all_days = pd.date_range(start_date, end_date, freq="D")
    classes_total = len(all_days)

    for mode, df_m in [("Offline", df_off), ("Online", df_on)]:
        for _, r in df_m.iterrows():
            rid = str(r["Reg ID"]); name = r["Name"]
            if att_all.empty:
                present_days = 0
            else:
                mask = (att_all["Reg ID"].astype(str) == rid) & att_all["Date"].between(start_ts, end_ts)
                present_days = att_all.loc[mask, "Date"].dt.normalize().nunique()
            abs_days = classes_total - present_days
            pct = present_days / classes_total if classes_total else 0.0
            students.append([rid, name, mode, classes_total, present_days, abs_days, pct, band_from_pct(pct)])

    cols = ["Reg ID","Name","Mode","Classes_Total","Presents_Total","Absents_Total","Attendance%_Total","Band_Total"]
    return pd.DataFrame(students, columns=cols)

def chart_band_distribution(df: pd.DataFrame, band_col: str, title: str, out_base: str) -> None:
    """Save a bar chart (PNG + SVG) for the band distribution."""
    counts = df[band_col].value_counts().reindex(["100%","High","Average","Low"]).fillna(0)
    fig = plt.figure(figsize=(12, 7))
    counts.plot(kind="bar")  # no custom colors/styles (kept simple)
    plt.title(title)
    plt.xlabel("Band")
    plt.ylabel("Students")
    plt.tight_layout()
    plt.savefig(out_base + ".png")
    plt.savefig(out_base + ".svg")
    plt.close(fig)

def save_xlsx(path: str, frames_by_sheet: dict) -> None:
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        for sheet, frame in frames_by_sheet.items():
            frame.to_excel(xw, sheet_name=sheet, index=False)

# ---------------- Build everything ----------------
if __name__ == "__main__":
    ensure_dir(OUT_DIR)

    # 1) Students (Master lists)
    df_master_off = make_students(N_OFFLINE, start_id=2000)
    df_master_on  = make_students(N_ONLINE,  start_id=3000)

    # 2) Attendance (last 14 days window for demo realism)
    start_14 = TODAY - timedelta(days=WINDOW_DAYS - 1)
    att_off = mark_attendance(df_master_off, start_14, TODAY, p_present=P_PRESENT_OFF)
    att_on  = mark_attendance(df_master_on,  start_14, TODAY, p_present=P_PRESENT_ON)

    # 3) Absentees (today only tabs — like your bot creates YYYY-MM-DD-offline/online)
    absent_off_today = absentees_for_day(df_master_off, att_off, str(TODAY))
    absent_on_today  = absentees_for_day(df_master_on,  att_on,  str(TODAY))

    # 4) Settings & ParentQueue (as in your main workbook)
    settings_tab = pd.DataFrame([{"DailyEasterEgg": "🙂", "StartTime": "09:00", "EndTime": "13:00"}])
    parent_queue_tab = pd.DataFrame(columns=["RegID","Date","Mode","Message","Status","CreatedAt","SentAt","Attempts"])

    # 5) Summaries (bi-weekly, monthly, course)
    biweekly_df = summarize_window(df_master_off, df_master_on, att_off, att_on, start_14, TODAY)
    monthly_df  = summarize_month(df_master_off, df_master_on, att_off, att_on, START_MONTH, END_MONTH)
    course_start = TODAY - timedelta(days=COURSE_DAYS - 1)
    course_df   = summarize_course(df_master_off, df_master_on, att_off, att_on, course_start, TODAY)

    # 6) MAIN WORKBOOK — mirrors your Google Sheets structure
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

    # 7) ABSENTEE WORKBOOKS (today’s tabs — just like your bot)
    save_xlsx(
        os.path.join(OUT_DIR, "offline_absentees_demo.xlsx"),
        { f"{TODAY}-offline": absent_off_today }
    )
    save_xlsx(
        os.path.join(OUT_DIR, "online_absentees_demo.xlsx"),
        { f"{TODAY}-online":  absent_on_today }
    )

    # 8) Standalone summary workbooks (so you can send each separately)
    biweekly_path = os.path.join(OUT_DIR, "biweekly_summary.xlsx")
    monthly_path  = os.path.join(OUT_DIR, "monthly_summary.xlsx")
    course_path   = os.path.join(OUT_DIR, "course_summary.xlsx")
    biweekly_df.to_excel(biweekly_path, index=False)
    monthly_df.to_excel(monthly_path, index=False)
    course_df.to_excel(course_path, index=False)

    # 9) High-DPI charts (PNG + SVG)
    chart_band_distribution(
        biweekly_df, "Band",
        "Bi-Weekly Attendance Bands",
        os.path.join(OUT_DIR, "biweekly_band_distribution")
    )
    chart_band_distribution(
        monthly_df, "Band_Month",
        "Monthly Attendance Bands",
        os.path.join(OUT_DIR, "monthly_band_distribution")
    )
    chart_band_distribution(
        course_df, "Band_Total",
        "Course Attendance Bands",
        os.path.join(OUT_DIR, "course_band_distribution")
    )

    print("\n✅ All demo files generated in:", os.path.abspath(OUT_DIR))
