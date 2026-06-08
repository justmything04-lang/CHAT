#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
 Generate GOOGLE_OAUTH_TOKEN — run this ONCE on your own computer.
═══════════════════════════════════════════════════════════════════════════════

WHY:
  A *service account* has ZERO Google Drive storage, so it cannot create Sheets
  on a personal Gmail (you get "storageQuotaExceeded"). Putting the file in a
  shared folder does NOT fix it — the file is still owned by the service account.

  The fix is to let the bot act as YOUR Google account. Then every Sheet it
  creates is owned by you and uses your free 15 GB quota. This script produces
  the token the bot needs.

ONE-TIME SETUP (in Google Cloud Console, same project as before):
  1. APIs & Services → OAuth consent screen
       • User type: External  → Create
       • Fill app name + your email, Save and Continue through the steps
       • Under "Test users" → ADD your own Gmail (the one that will own sheets)
  2. APIs & Services → Credentials → + Create Credentials → OAuth client ID
       • Application type: Desktop app  → Create
       • Download JSON → save it next to this file as  client_secret.json
  3. Make sure Google Drive API + Google Sheets API are enabled (they already are).

RUN IT:
       pip install gspread
       python generate_oauth_token.py
  A browser opens → sign in with the OWNER Gmail → Allow.
  The script prints a long GOOGLE_OAUTH_TOKEN value.

THEN:
  • Render → your service → Environment
       - Add   GOOGLE_OAUTH_TOKEN = <the printed value>
       - You can DELETE  GOOGLE_CREDENTIALS_JSON  (service account no longer used)
  • Manual Deploy. Done — onboarding will now create sheets in your Drive.
═══════════════════════════════════════════════════════════════════════════════
"""
import base64
import json
import os
import sys

try:
    import gspread
except ImportError:
    sys.exit("❌ gspread not installed. Run:  pip install gspread")

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(HERE, "client_secret.json")


def main() -> None:
    if not os.path.exists(CLIENT_SECRET):
        sys.exit(
            "❌ client_secret.json not found next to this script.\n"
            "   Create a *Desktop app* OAuth client in Google Cloud Console,\n"
            "   download the JSON, and save it here as client_secret.json.\n"
            "   (See the instructions at the top of this file.)"
        )

    with open(CLIENT_SECRET, encoding="utf-8") as f:
        client_config = json.load(f)

    print("\n🔐 A browser window will open.")
    print("   Sign in with the Gmail that should OWN the study sheets, then click Allow.\n")

    # Interactive flow — returns (client, authorized_user_json_string)
    gc, authorized_user = gspread.oauth_from_dict(client_config)

    if not isinstance(authorized_user, str):
        authorized_user = json.dumps(authorized_user)

    # Sanity check: confirm the credentials actually work
    try:
        gc.list_spreadsheet_files()
        print("✅ Authorization succeeded — the token works.\n")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Token generated but a test call failed: {exc}")
        print("   (It may still work on the server — continue and try a deploy.)\n")

    token_b64 = base64.b64encode(authorized_user.encode("utf-8")).decode("utf-8")

    print("=" * 72)
    print("Copy this ENTIRE value into Render → Environment as GOOGLE_OAUTH_TOKEN")
    print("(it is one long line — select all of it):\n")
    print(token_b64)
    print("\n" + "=" * 72)
    print("⚠️  Treat this like a password — it grants access to your Google Drive.")


if __name__ == "__main__":
    main()
