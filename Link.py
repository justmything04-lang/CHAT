Awesome — we can do this cleanly with Telegram’s one-time “join request” invite links + your existing /start deep links.

Flow recap (exactly what you asked):
	•	Recording students click a special deep link → bot immediately generates a one-use group link bound to that Telegram user → if they share it, others’ join requests get auto-rejected.
	•	Normal (online) students click another deep link → finish registration + parent linking → bot then generates the same kind of one-use group link, bound to that user → sharing won’t work.

This uses:
	•	create_chat_invite_link(..., creates_join_request=True, member_limit=1).
	•	A join-request handler that approves only if the requestor’s user_id matches the user we intended; otherwise declines.
	•	A tiny “Invites” tab in your Google Sheet to keep state across restarts.

Below are paste-ready blocks that fit your current file.

⸻

1) .env (append)

# Your batch supergroup chat id (negative id)
BATCH_GROUP_ID=-1001234567890

# Optional: auto-expiry (minutes) for one-time links; 0 = no expiry
INVITE_EXPIRE_MIN=0

Make sure your bot is an admin in that group with “Invite via Link” and “Approve Join Requests”.

⸻

2) Create (or auto-create) an “Invites” sheet (put with other sheet defs)

Paste below your ParentQueue block:

# ---------------- Invites sheet (persist one-time links) ----------------
try:
    invites_sheet = client.open_by_key(SHEET_ID).worksheet("Invites")
except gspread.exceptions.WorksheetNotFound:
    invites_sheet = client.open_by_key(SHEET_ID).add_worksheet(title="Invites", rows="2000", cols="8")
    invites_sheet.update("A1:H1", [[
        "InviteLink","GroupId","UserId","Kind","Status","CreatedAt","ExpireAt","UsedAt"
    ]])


⸻

3) Helpers for one-time links (put near other helpers)

def _invite_row(inv_link, group_id, user_id, kind, expire_at_str):
    return [inv_link, str(group_id), str(user_id), kind, "ACTIVE", now_ts(), expire_at_str or "", ""]

def invites_store(inv_link, group_id, user_id, kind, expire_at=None):
    try:
        invites_sheet.append_row(
            _invite_row(inv_link, group_id, user_id, kind, expire_at.strftime("%Y-%m-%d %H:%M:%S") if expire_at else ""),
            value_input_option='USER_ENTERED'
        )
    except Exception as e:
        print("invites_store error:", e)

def invites_find_by_link(link):
    try:
        rows = invites_sheet.get_all_records()
        for i, r in enumerate(rows, start=2):
            if str(r.get("InviteLink","")).strip() == str(link).strip():
                return i, r
    except Exception as e:
        print("invites_find_by_link error:", e)
    return None, None

def invites_mark_used(row_idx):
    try:
        invites_sheet.update_cell(row_idx, 5, "USED")   # Status
        invites_sheet.update_cell(row_idx, 8, now_ts()) # UsedAt
    except Exception as e:
        print("invites_mark_used error:", e)

def invites_revoke(link):
    # Optional: you can revoke an invite link via the Bot API if you want.
    # Not strictly needed because we use join-requests + approval filter.
    pass

def create_one_time_invite_for(user_id, kind="normal"):
    """
    Creates a join-request invite link that only this user can actually get approved for.
    We also store it in the Invites sheet.
    """
    group_id = int(os.getenv("BATCH_GROUP_ID","0"))
    if not group_id:
        raise RuntimeError("BATCH_GROUP_ID missing")

    # Optional expiry
    mins = int(os.getenv("INVITE_EXPIRE_MIN","0") or "0")
    expire_dt = None
    if mins > 0:
        expire_dt = datetime.now(ZoneInfo(TIMEZONE)) + timedelta(minutes=mins)
        expire_unix = int(expire_dt.timestamp())
    else:
        expire_unix = None

    # Create invite link that requires approval
    # member_limit=1 keeps it single-use; creates_join_request=True prevents auto-join
    try:
        link_obj = bot.create_chat_invite_link(
            chat_id=group_id,
            name=f"{kind}-{user_id}-{int(time.time())}",
            expire_date=expire_unix,
            member_limit=1,
            creates_join_request=True
        )
        inv_link = link_obj.invite_link
        invites_store(inv_link, group_id, user_id, kind, expire_dt)
        return inv_link
    except Exception as e:
        print("create_one_time_invite_for error:", e)
        raise


⸻

4) Deep-link intake: recording vs normal (modify your /start handler)

Find your @bot.message_handler(commands=['start']) and add these branches above the parent deep-link block or right after you parse args:

@bot.message_handler(commands=['start'])
def start_cmd(msg):
    txt = (msg.text or "").strip()
    if " " in txt:
        _, args = txt.split(" ", 1)
    else:
        args = ""

    uid = str(msg.from_user.id)

    # 4.a) Recording students deep-link: /start rec_<token or id>
    if args.startswith("rec_"):
        # You can validate token here if Academy sends a signed token.
        # For now we treat it as authorized.
        try:
            link = create_one_time_invite_for(uid, kind="recording")
            safe_reply(msg,
                "🎧 Recording student detected.\n"
                "Tap this one-time link to join your class group (join request will be auto-approved for you):\n"
                f"{link}\n\n"
                "Note: This link won’t work for anyone else."
            )
        except Exception as e:
            safe_reply(msg, f"⚠️ Could not create your group link: {e}")
        return

    # 4.b) Normal (online) students: /start norm_<token or id>
    # We will issue the group link after onboarding (registration + parent linking).
    if args.startswith("norm_"):
        # mark that this user is a normal student awaiting onboarding completion
        try:
            # minimal in-memory flag; if you want persistence, add a column to MasterList
            registration_pending_norm = registration_pending.get(msg.from_user.id) or False
            bot.set_my_commands # no-op to silence linter
        except Exception:
            pass
        # store a flag in memory
        try:
            global _invite_after_onboarding
        except NameError:
            _invite_after_onboarding = set()
        _invite_after_onboarding.add(msg.from_user.id)

        # continue to your normal start flow below (will show teacher panel or student menu)
        # (do not return here)

This sets up two separate /start paths: rec_… and norm_….
If you want to validate the token the academy gives (recommended), add a small HMAC check in the rec_ / norm_ branches before proceeding.

⸻

5) Issue invite after normal student completes onboarding

In your register_parent_number handler (you already set ParentLinked=Yes there), append this at the very end, just before sending the “Parent number saved” success message (or right after it):

    # If this user came via norm_ deep-link, and is now linked -> send one-time invite
    try:
        global _invite_after_onboarding
    except NameError:
        _invite_after_onboarding = set()

    if msg.from_user.id in _invite_after_onboarding:
        # Check linked again to be safe
        sheet, _mode = find_sheet_for_reg(str(uid))
        info2 = get_parent_info(sheet, str(uid)) if sheet else {}
        linked2 = str(info2.get("ParentLinked","")).strip().lower() == "yes"
        if linked2:
            try:
                inv = create_one_time_invite_for(uid, kind="normal")
                safe_send_chat(msg.chat.id,
                    "✅ Onboarding done!\n"
                    "Here is your one-time group link (works only for you):\n"
                    f"{inv}\n\n"
                    "Tap it and send the join request — I’ll auto-approve you."
                )
                _invite_after_onboarding.discard(msg.from_user.id)
            except Exception as e:
                print("Post-onboarding invite error:", e)


⸻

6) Approve only the intended user; decline everyone else

Add this anywhere after your other handlers:

# ---------------- Join Request Guard ----------------
@bot.chat_join_request_handler(func=lambda req: True)
def handle_join_request(req):
    """
    Approves the join request only if:
      - The invite link is one we created, AND
      - The request.user.id matches the UserId we stored for that link, AND
      - Status is ACTIVE and not expired.
    Else declines.
    """
    try:
        inv = req.invite_link.invite_link if req.invite_link else ""
        row_idx, rec = invites_find_by_link(inv)
        if not row_idx or not rec:
            print("join_request: invite not recognized", inv)
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        status = str(rec.get("Status","")).upper()
        intended_uid = str(rec.get("UserId","")).strip()
        grp = int(rec.get("GroupId", req.chat.id))
        expire_at = str(rec.get("ExpireAt","")).strip()

        # expiry check (if set)
        if expire_at:
            try:
                exp = datetime.strptime(expire_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(TIMEZONE))
                if datetime.now(ZoneInfo(TIMEZONE)) > exp:
                    print("join_request: invite expired")
                    bot.decline_chat_join_request(req.chat.id, req.from_user.id)
                    return
            except Exception:
                pass

        if status != "ACTIVE":
            print("join_request: invite not active")
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        if str(req.from_user.id) != intended_uid:
            print(f"join_request: user mismatch expected={intended_uid} got={req.from_user.id}")
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        # All good → approve and mark USED
        bot.approve_chat_join_request(grp, req.from_user.id)
        invites_mark_used(row_idx)
        print(f"✅ Approved {req.from_user.id} via guarded invite.")
    except Exception as e:
        print("handle_join_request error:", e)
        try:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception:
            pass

Because we approve only the owner of that link, sharing the link won’t admit others — their requests get declined.

⸻

7) Keyboard buttons (already done)

You already added:
	•	"📅 Monthly Report" → /monthly
	•	"📘 Course Summary" → /course
	•	"📅 Bi-Weekly Report" → /biweekly

No change needed here.

⸻

Notes & Options
	•	Persist “norm_ pending” flag:
The in-memory _invite_after_onboarding set resets on restart.
If you want persistence, add a column InviteAfterOnboarding in MasterList / OnlineMasterList and flip it to Yes/No.
	•	Token validation (recommended):
Ask the academy to send /start rec_<jwt> and /start norm_<jwt> where the JWT contains {uid, kind, exp} and verify with a shared secret to prevent spoofing.
	•	Offline students:
If you also want this for offline, make a third deep link /start off_<jwt> and reuse the same flow.
	•	Re-sending the link:
If students lose the link before using it, you can let them DM /grouplink and generate a new one-time link (and mark any older ACTIVE links as REVOKED).

⸻

What this gives you now
	•	✅ Recording: instant one-time link (bound to user).
	•	✅ Normal: post-onboarding one-time link.
	•	✅ Non-shareable: others’ join requests are auto-declined.
	•	✅ Fully integrated into your existing Sheets + bot structure.

If you want, I can also add a /grouplink command for teacher/admin to regenerate a user’s one-time link on demand.










    safe_reply(msg, TPL_PARENT_WELCOME)
    deliver_pending_for_reg(reg_id)

    # 🎯 NEW: if onboarding is complete now, DM the student their one-time group link
    try:
        if is_onboarding_complete(reg_id):
            link = create_one_time_invite_for(int(reg_id), kind="student")
            safe_send_chat(int(reg_id),
                f"✅ Onboarding complete!\n"
                f"Here is your permanent group link:\n{link}"
            )
            print(f"[ONBOARD] Sent one-time group link to student {reg_id}")
    except Exception as e:
        print("[ONBOARD] Failed to create/send student one-time link:", e)

    return
