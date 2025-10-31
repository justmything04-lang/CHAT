Nice — below is one combined, copy-paste ready set of changes that brings everything together:
	•	Adds a small persistent Control sheet + helpers for multi-process dedupe.
	•	Adds publish_top3_to_teacher_and_topic() so Top3 can be triggered programmatically.
	•	Replaces auto_eod_worker, biweekly_worker, monthly_worker, weekly_summary_worker with the updated logic (30-day monthly windows anchored to Settings start, biweekly same as before, weekly Top3 on Sundays, EOD reliable at EndTime -5min and deduped).
	•	Adds the publish_top3 call into send_course_summary_report().

For each change I show:
	1.	Where to add/replace (with 3 lines before and after to help you find the spot), and
	2.	The exact replacement / insertion code.

⸻

A — Add Control sheet helpers

Where to add: After your invites_sheet block (search for the block that creates Invites sheet). Use the 3 lines context to find it.

Find (3 lines prev + lines to match + 3 after):

    invites_sheet.update("A1:H1", [[
        "InviteLink","GroupId","UserId","Kind","Status","CreatedAt","ExpireAt","UsedAt"
    ]])
# ---------------- Simple cache (TTL = 60s) ----------------
CACHE_TTL = 60
_cache = {

Replace / Insert (add this block right after the invites_sheet creation — i.e. immediately before # ---------------- Simple cache (TTL = 60s)):

# ---------- Persistent "Control" helpers (to avoid multi-process duplicates) ----------
try:
    control_sheet = client.open_by_key(SHEET_ID).worksheet("Control")
except gspread.exceptions.WorksheetNotFound:
    control_sheet = client.open_by_key(SHEET_ID).add_worksheet(title="Control", rows="200", cols="4")
    # header Key | Value | UpdatedAt
    control_sheet.update("A1:C1", [["Key","Value","UpdatedAt"]])

def _control_get(key):
    """Return value (string) for a key or None"""
    try:
        rows = control_sheet.get_all_records()
        for r in rows:
            if str(r.get("Key","")).strip() == str(key):
                return str(r.get("Value","")).strip()
    except Exception as e:
        print("_control_get error:", e)
    return None

def _control_set(key, value):
    """Upsert key->value and UpdatedAt in Control sheet"""
    try:
        rows = control_sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("Key","")).strip() == str(key):
                control_sheet.update_cell(i, 2, str(value))
                control_sheet.update_cell(i, 3, now_ts())
                return True
        # not found -> append
        control_sheet.append_row([str(key), str(value), now_ts()], value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print("_control_set error:", e)
        return False
# ---------------- Simple cache (TTL = 60s) ----------------
CACHE_TTL = 60
_cache = {


⸻

B — Add publish_top3_to_teacher_and_topic() helper

Where to add: After your existing send_top3(message) function (search for the end of send_top3 — find the last except block and the closing lines). Use the 3-line context.

Find (3 lines prev + match + 3 after):

        safe_reply(message, offline_msg + "\n\n" + online_msg)
        _post_public(offline_msg + "\n\n" + online_msg)
    except Exception as e:
        safe_reply(message, f"⚠️ Error generating Top 3: {e}")
        print("Top3 error:", e)

Insert (directly after the send_top3 function):

# ---------- Helper to run Top3 programmatically ----------
from types import SimpleNamespace as SNS

def publish_top3_to_teacher_and_topic():
    """
    Run the Top3 logic without depending on a Telegram message object.
    Sends combined Top3 to TEACHER_ID (DM) and posts to the public topic.
    """
    try:
        absentee_file = client.open_by_key(ABSENTEE_SHEET_ID)

        def build_top3(tabs, students, total_classes, label):
            if total_classes == 0:
                return f"⚠️ No {label.lower()} attendance history yet."

            stats = {str(s.get("Reg ID")): {"Name": s.get("Name"), "Absent": 0} for s in students}
            for ws in tabs:
                absentees = _gs_read(lambda: ws.get_all_records())
                for a in absentees:
                    rid = str(a.get("Reg ID", ""))
                    if rid in stats:
                        stats[rid]["Absent"] += 1

            results = []
            for reg_id, data in stats.items():
                absent = data["Absent"]
                present = total_classes - absent
                percent = (present / total_classes) * 100 if total_classes else 0
                results.append((data["Name"], reg_id, present, absent, percent))
            results.sort(key=lambda x: (-x[4], -x[2]))

            msg = f"🏆 {label} Top Performers (out of {total_classes} classes):\n\n"
            rank = 1
            prev_percent = None
            group = []
            rank_emojis = {1: "🥇 Top 1", 2: "🥈 Top 2", 3: "🥉 Top 3"}
            for name, reg, present, absent, percent in results:
                if prev_percent is None or percent < prev_percent:
                    if rank > 3:
                        break
                    if group:
                        msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                        for g in group:
                            msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                        msg += "\n"
                        group = []
                    prev_percent = percent
                    rank += 1
                group.append((name, reg, present, absent, percent))

            if group and rank-1 <= 3:
                msg += f"{rank_emojis[rank-1]} ({prev_percent:.1f}%):\n"
                for g in group:
                    msg += f"• {g[0]} ({g[1]}) - ✅ {g[2]}, ❌ {g[3]}, 📊 {g[4]:.1f}%\n"
                msg += "\n"

            return msg.strip()

        offline_tabs = [ws for ws in absentee_file.worksheets() if ws.title.endswith("-offline")]
        offline_msg = build_top3(offline_tabs, get_cached_master_list(), len(offline_tabs), "Offline")

        online_file = client.open_by_key(ONLINE_ABSENTEE_SHEET_ID)
        online_tabs = [ws for ws in online_file.worksheets() if ws.title.endswith("-online")]
        online_msg = build_top3(online_tabs, get_cached_online_master_list(), len(online_tabs), "Online")

        combined = offline_msg + "\n\n" + online_msg

        if TEACHER_ID:
            safe_send_chat(TEACHER_ID, combined)
        _post_public(combined)
        print("✅ Auto Top3 published (teacher + topic).")
    except Exception as e:
        print("publish_top3_to_teacher_and_topic error:", e)


⸻

C — Replace auto_eod_worker() (remove Top3 from EOD or keep as you want)

You previously asked two variants; you said Top3 should NOT run with EOD, so I supply the version without Top3. (If you want Top3 with EOD, swap in the alternate variant from earlier instructions.)

Find (3 lines prev + match + 3 after):
Search for the existing function header and first lines:

def auto_eod_worker():
    """
    Checks every 2 minutes.
    Triggers EOD 5 minutes BEFORE EndTime (primary), and

and the end block where it sleeps/error prints.

Replace entire auto_eod_worker() body with:

def auto_eod_worker():
    """
    Checks every 2 minutes.
    Triggers EOD 5 minutes BEFORE EndTime (primary), and
    if still not done, triggers again 2 hours AFTER EndTime (fallback).
    Uses sheet-tab existence and Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            s = get_cached_settings()
            end_str = s.get("EndTime", "23:59").strip()
            today   = get_today_date()

            # build today's localized end time
            try:
                end_dt = datetime.strptime(today + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = datetime.now(ZoneInfo(TIMEZONE))

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)
            now_local       = datetime.now(ZoneInfo(TIMEZONE))

            # persistent guard: check if we already ran EOD today (control key)
            last_eod = _control_get("LastEOD") or ""
            if last_eod == today:
                time.sleep(120)
                continue

            # also fallback to sheet-existence check (safe)
            if _is_eod_done_for(today):
                # mark control so other instances don't also run
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Auto EOD (primary, -5 min) window…")
                # run and mark
                generate_eod_and_notify()
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Auto EOD (fallback, +2h) window…")
                if not _is_eod_done_for(today):
                    generate_eod_and_notify()
                _control_set("LastEOD", today)
                time.sleep(120)
                continue

            time.sleep(120)

        except Exception as e:
            print("auto_eod_worker error:", e)
            time.sleep(180)


⸻

D — Replace biweekly_worker() (run Top3 with bi-weekly)

Find (3 lines prev + match + 3 after):
Search for the function header:

def biweekly_worker():
    """
    Checks every 2 minutes.
    """

Replace entire biweekly_worker() body with:

def biweekly_worker():
    """
    Checks every 2 minutes.
    On the LAST day of the current 14-day window:
      - trigger 5 minutes BEFORE EndTime (primary)
      - if missed, fallback 2 hours AFTER EndTime
    Uses Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            today     = now_local.date()

            start = _get_class_start_date()
            win_start, win_end, is_boundary = _current_biweekly_window(today, start)

            if not is_boundary:
                time.sleep(120)
                continue

            key = f"BiWeekly_{win_end}"
            last = _control_get("LastBiWeekly") or ""
            if last == str(win_end):
                time.sleep(120)
                continue

            s = get_cached_settings()
            end_str = s.get("EndTime","23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Bi-Weekly (primary, -5 min) window…")
                send_biweekly_report()
                _control_set("LastBiWeekly", str(win_end))
                # publish Top3 together with Bi-Weekly
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Bi-Weekly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Bi-Weekly (fallback, +2h) window…")
                send_biweekly_report()
                _control_set("LastBiWeekly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Bi-Weekly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            time.sleep(120)
        except Exception as e:
            print("biweekly_worker error:", e)
            time.sleep(180)


⸻

E — Replace monthly_worker() (30-day windows anchored to Settings start)

Find (3 lines prev + match + 3 after):
Search for def monthly_worker(): block header.

Replace entire monthly_worker() body with:

def monthly_worker():
    """
    Checks every 2 minutes.
    Trigger when 30-day window ends (30 days after class start cycle), using Settings start date as anchor.
    Uses Control sheet to avoid duplicates across processes.
    """
    while True:
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            today     = now_local.date()

            start = _get_class_start_date()
            # compute 30-day windows:
            days = _days_since(start, today)
            if days < 0:
                time.sleep(120); continue
            idx = days // 30
            win_start = start + timedelta(days=30*idx)
            win_end = win_start + timedelta(days=29)  # 30-day window inclusive
            is_boundary = (today == win_end)

            if not is_boundary:
                time.sleep(120)
                continue

            key = f"Monthly_{win_end.strftime('%Y-%m-%d')}"
            last = _control_get("LastMonthly") or ""
            if last == str(win_end):
                time.sleep(120)
                continue

            s = get_cached_settings()
            end_str = s.get("EndTime","23:59").strip()
            try:
                end_dt = datetime.strptime(str(today) + " " + end_str, "%Y-%m-%d %H:%M")
                end_dt = end_dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            except Exception:
                end_dt = now_local

            pre_trigger_dt  = end_dt - timedelta(minutes=5)
            post_trigger_dt = end_dt + timedelta(hours=2)

            if pre_trigger_dt <= now_local < post_trigger_dt:
                print("⏱️ Monthly (primary, -5 min) window…")
                send_monthly_report()
                _control_set("LastMonthly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Monthly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            if now_local >= post_trigger_dt:
                print("⏱️ Monthly (fallback, +2h) window…")
                send_monthly_report()
                _control_set("LastMonthly", str(win_end))
                try:
                    publish_top3_to_teacher_and_topic()
                except Exception as e:
                    print("Monthly -> Top3 publish error:", e)
                time.sleep(120)
                continue

            time.sleep(120)
        except Exception as e:
            print("monthly_worker error:", e)
            time.sleep(180)


⸻

F — Replace weekly_summary_worker() (Sunday Top3 + control)

Find (3 lines prev + match + 3 after):
Search for def weekly_summary_worker(): block.

Replace the function body with:

def weekly_summary_worker():
    while True:
        try:
            now = datetime.now(ZoneInfo(TIMEZONE))
            # Sunday ~09:00 window
            if now.weekday() == 6 and now.hour == 9 and now.minute < 5:
                last_week = _control_get("LastWeekly") or ""
                this_key = now.strftime("%Y-%U")  # year-week key
                if last_week != this_key:
                    off_list = master_sheet.get_all_records()
                    on_list = online_master_sheet.get_all_records() if online_master_sheet else []

                    off_total = len(off_list)
                    on_total = len(on_list)
                    off_linked = sum(1 for r in off_list if str(r.get("ParentChatId","")).strip())
                    on_linked  = sum(1 for r in on_list if str(r.get("ParentChatId","")).strip())

                    msg = TPL_FACULTY_WEEKLY.format(
                        off_linked=off_linked, off_total=off_total,
                        on_linked=on_linked, on_total=on_total
                    )
                    if TEACHER_ID:
                        safe_send_chat(TEACHER_ID, msg)

                    # publish Top3 on Sunday too
                    try:
                        publish_top3_to_teacher_and_topic()
                    except Exception as e:
                        print("Weekly -> Top3 publish error:", e)

                    _control_set("LastWeekly", this_key)
            time.sleep(300)
        except Exception as e:
            print("Weekly summary error:", e)
            time.sleep(600)


⸻

G — Ensure send_course_summary_report() triggers Top3

Where to edit: Find the end of send_course_summary_report() — search near where it does print("✅ Course summary done.").

Find (3 lines prev + match + 3 after):

    _enforce_low_in_app({rid for rid, *_ in (risk_off + risk_on)}, win_start, win_end)
    print("✅ Course summary done.")

Replace with (add publish_top3 call right before printing):

    _enforce_low_in_app({rid for rid, *_ in (risk_off + risk_on)}, win_start, win_end)

    try:
        publish_top3_to_teacher_and_topic()
    except Exception as e:
        print("Course Summary -> Top3 publish error:", e)

    print("✅ Course summary done.")


⸻

H — Small checklist & testing steps (do after you paste/replace)
	1.	Restart a single instance first (so Control sheet is created and seeded).
	2.	Inspect Control sheet (it should be created with header). After runs you’ll see keys like: LastEOD, LastBiWeekly, LastMonthly, LastWeekly.
	3.	Test EOD:
	•	Temporarily set Settings!C2 (EndTime) a minute or two in the future (HH:MM), watch logs for:
⏱️ Auto EOD (primary, -5 min) window… or ⏱️ Auto EOD (fallback, +2h).
	•	Confirm absentee tabs YYYY-MM-DD-offline and -online are created and parents are queued/sent.
	4.	Test Bi-Weekly / Monthly:
	•	Temporarily set Settings!D2 (class start date) so that today’s date is a boundary (or change system date) to trigger biweekly/monthly worker windows. Watch logs for “Bi-Weekly (primary, -5 min) window…” or “Monthly (primary, -5 min) window…”.
	5.	Test Weekly Top3:
	•	Set your system date/time to Sunday 09:00 or temporarily change the if now.weekday() == 6 and now.hour == 9 condition to match current minute, then watch logs.
	6.	Manual commands still work: /top3, /eod, /biweekly, /monthly, /course — manual runs should not be blocked by control keys but auto workers will avoid duplicate runs.

⸻

I — Summary of behavior after changes
	•	EOD: runs automatically 5 minutes before EndTime (primary), fallback +2h; uses Control sheet to avoid duplicates; creates absentee tabs and notifies parents; does not automatically run Top3 (by your later instruction).
	•	Bi-Weekly: runs on biweekly window boundary (last day of current 14-day window), primary at EndTime -5m, fallback +2h; writes summary sheet; also publishes Top3 and notifies parents + optional academy lock.
	•	Monthly: now runs on 30-day windows anchored from Settings!D2 (class start), not calendar month; same pre/post trigger windows; also publishes Top3.
	•	Course Summary: unchanged logic but now publishes Top3 at the end.
	•	Weekly: runs Sunday ~09:00 and publishes Top3.
	•	Top3: can now be published programmatically by calling publish_top3_to_teacher_and_topic(); manual /top3 still works.
	•	Multi-process safe: using Control sheet keys (LastEOD, LastBiWeekly, LastMonthly, LastWeekly) avoids double sends if you have >1 container/process.

⸻

If you want I can now:
	•	(A) produce a single patched file (full file) with all replacements applied and send it, or
	•	(B) produce a compact diff (unified diff style) showing exact replacements with line numbers (if you tell me approximate line numbers), or
	•	(C) walk you through deploying and testing one worker at a time.

Which do you prefer?
