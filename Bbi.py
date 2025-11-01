
Nice — I inspected your pasted file and found the real causes of the SyntaxError: expected 'except' or 'finally' block and the IndentationError you saw. The root problems are (A) stray non-ASCII “smart” characters / accidental text injected inside an except block (which leaves a try: without a matching except/finally), and (B) a few places where a for block was indented incorrectly (extra leading spaces), causing unexpected indent.

Below I give concrete, copy-pasteable patches you can apply. For each patch I show: 3 lines before, the problematic lines, and 3 lines after (so you can find the spot easily), then a corrected replacement block. Do the replacements exactly (preserve indentation of function bodies — 4 spaces).

⸻

PATCH 1 — fix stray characters in send_top3 except block (the primary cause of the expected 'except' syntax error)

Why: inside send_top3 you have an except block that ends with a non-ASCII closing quote and extra user text (“ wait for the next half) — that inserted text breaks Python parsing and leaves an open try: without a valid except/finally.

Find (context lines) — locate this block near the end of your send_top3 function (search for publish_top3_to_teacher_and_topic error):

        print("publish_top3_to_teacher_and_topic error:",e)
        if ADMIN_ID:
            try:
                safe_send_chat(ADMIN_ID, f"⚠️ publish_top3_to_teacher_and_topic error: {e}")
            except Exception: pass “ wait for the next half

Replace with this (corrected):

        print("publish_top3_to_teacher_and_topic error:", e)
        if ADMIN_ID:
            try:
                safe_send_chat(ADMIN_ID, f"⚠️ publish_top3_to_teacher_and_topic error: {e}")
            except Exception:
                pass

Notes:
	•	Remove the smart quote “ and the wait for the next half stray text.
	•	Make sure the except Exception: uses a normal ASCII colon and that pass is on the next (indented) line or the same line as the except (I prefer separate line as shown).
	•	This fix will remove the unmatched try:/except problem that caused the parser to later complain at the next def (your _is_eod_done_for) with expected 'except' or 'finally' block.

⸻

PATCH 2 — fix unexpected indent in send_biweekly_report

You reported IndentationError: unexpected indent for a for student in get_cached_master_list(): block. In the posted code that loop had extra leading spaces (it was indented further than the surrounding code).

Find (problem lines) — search for the end of send_biweekly_report() where you printed the final summary:

    print("✅ Bi-Weekly: topic posted, admin notified, sheet updated, parents cautioned, app lock attempted.")

      for student in get_cached_master_list():
        msg_s = APP_STUDENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        msg_p = APP_PARENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        safe_send_chat(student["Reg ID"], msg_s)
        if student.get("ParentChatId"):
            safe_send_chat(student["ParentChatId"], msg_p)
        db.update_streak(student["Reg ID"], boost=True)

Replace with this (dedented to the same indentation level as the print — 4 spaces inside the function):

    print("✅ Bi-Weekly: topic posted, admin notified, sheet updated, parents cautioned, app lock attempted.")

    for student in get_cached_master_list():
        msg_s = APP_STUDENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        msg_p = APP_PARENT_HIGH.format(
            student_name=student["Name"],
            period_type="Bi-Weekly",
            range_or_course=f"{win_start}–{win_end}"
        )
        safe_send_chat(student["Reg ID"], msg_s)
        if student.get("ParentChatId"):
            safe_send_chat(student["ParentChatId"], msg_p)
        db.update_streak(student["Reg ID"], boost=True)

Notes:
	•	Make sure there are exactly 4 spaces at function body level before for (no extra spaces/tabs). The unexpected indent error occurs when indentation level doesn’t match rest of function.

⸻

PATCH 3 — similar dedent fixes for send_monthly_report() and send_course_summary_report()

You had identical loops in monthly/course functions that showed the same pattern — ensure they use the same indentation as the function body. In both places you had:

    for student in get_cached_master_list():
        ...
        db.update_streak(student["Reg ID"], boost=True)

Make sure those for loops are indented exactly 4 spaces (not 6, not tabs mixed). If you pasted earlier and got unexpected indent for monthly, apply the same correction.

Example replacement (monthly):

Find the block:

    for student in get_cached_master_list():
        msg_s = APP_STUDENT_HIGH.format(
            student_name=student["Name"],
            period_type="Monthly",
            range_or_course=f"{win_start}–{win_end}"
        )
        ...
        db.update_streak(student["Reg ID"], boost=True)

Ensure it is exactly as shown above with 4 spaces indentation for the for line.

Do the same for the Course Summary loop.

⸻

BONUS PATCH 4 — remove any stray “smart quotes” and unicode directional quotes across file

You should remove smart quotes (“ ” ‘ ’) and replace with ASCII " or '. Stray smart quotes commonly break Python if they appear outside strings or mixed in code.

Run these commands in your build / local environment to locate and optionally fix them:

Locate occurrences:

# find any smart single/double quotes
grep -nP '[\u2018\u2019\u201C\u201D]' 11111.py || true

Replace them (non-destructive — creates a backup file):

# replace smart double quotes with ascii double quotes
perl -0777 -pe 's/[\x{201C}\x{201D}]/"/g' 11111.py > 11111.fixed.py
# replace smart single quotes with ascii single quotes
perl -0777 -pe "s/[\x{2018}\x{2019}]/'/g" 11111.fixed.py > 11111.fixed2.py
# inspect diffs then overwrite if OK
diff -u 11111.py 11111.fixed2.py | sed -n '1,200p'
# if looks fine:
mv 11111.fixed2.py 11111.py

(If perl isn’t available, use sed variants or open in an editor and replace smart quotes.)

⸻

How to verify after applying patches (commands for your Render build or locally)

Run these in your build / shell (you already had similar commands):
	1.	Install requirements (you already have this):

pip install --upgrade pip && pip install -r requirements.txt

	2.	Quick syntax check (fast):

python -m py_compile 11111.py

If py_compile returns no output and exit status 0 — syntax is OK.
	3.	Run the helper to find unclosed try: (the script you showed earlier). Save it as find_unclosed_try.py and run:

python find_unclosed_try.py 11111.py

It will report potential dangling try: indent mismatches (line numbers).
	4.	Optional lint + autoformat:

	•	Use black to standardize indentation (won’t fix logic but will fix spacing):

pip install black
black 11111.py

	•	Use flake8 to find other indentation/syntax/style issues:

pip install flake8
flake8 11111.py --max-line-length=120


⸻

Why you were seeing SyntaxError: expected 'except' or 'finally' block at the later def line

Python flagged the next def because earlier in the file there was a try: that the parser did not find a matching except/finally for — that commonly happens when stray characters or user text are placed where the except block should be. Fixing the stray characters in the send_top3 except block (PATCH 1) will remove that parsing error.

⸻

Quick checklist — do these 4 things now
	1.	Apply PATCH 1 (remove the smart quote + stray text in the send_top3 except block).
	2.	Apply PATCH 2 (dedent the biweekly for student loop to match function body).
	3.	Apply PATCH 3 (verify/dedent monthly & course loops).
	4.	Run python -m py_compile 11111.py and python find_unclosed_try.py 11111.py and grep -nP '[\u201C\u201D\u2018\u2019]' 11111.py to confirm no smart quotes remain.

⸻

If you want, I can now:
	•	produce one combined patch file (a small unified diff) with the exact replacements (so you can patch it), or
	•	show the exact line numbers to edit (I can approximate from your pasted file, but I recommend running grep -n "publish_top3_to_teacher_and_topic error" to find exact line numbers in your version and then apply the replacement).

Tell me which you prefer and I’ll output the unified diff / patch text you can apply with patch or paste directly.
