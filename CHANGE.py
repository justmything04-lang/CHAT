# Telegram
BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TEACHER_ID=1390359146
ADMIN_ID=123456789
BOT_USERNAME=YourBotUsername   # without @

# Sheets
SHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ABSENTEE_SHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxx     # offline absentee workbook
ONLINE_ABSENTEE_SHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxx  # online absentee workbook

TIMEZONE=Asia/Kolkata
CLASS_LAT=12.9551501
CLASS_LON=80.1696185
RADIUS_METERS=250

# Google service JSON (escaped string)
SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'

# Render/Keep-Alive
RENDER_EXTERNAL_URL=your-service.onrender.com
WEBHOOK_URL=https://your-service.onrender.com/<BOT_TOKEN>
KEEP_ALIVE_URL=https://your-service.onrender.com

# WhatsApp Business Cloud API (only used once at registration)
WHATSAPP_TOKEN=EAAG...your_meta_long_token...
WHATSAPP_PHONE_ID=123456789012345

# Message templates (you can edit anytime, code auto-uses)
PARENT_WELCOME_MSG="Hello 👋, you are now linked as a parent for updates about your child’s attendance. Please do not reply."
PARENT_ABSENT_MSG="⚠️ Your child {student_name} ({reg_id}) was absent on {date} ({mode})."
PARENT_INVITE_MSG="Hello 👋 from the academy. Please install Telegram and start our bot to receive updates: https://t.me/{bot_username}?start=parent_{reg_id}"
FACULTY_REPORT_MSG="📊 Weekly Report:\nOffline parents linked: {off_linked}/{off_total}\nOnline parents linked: {on_linked}/{on_total}"
