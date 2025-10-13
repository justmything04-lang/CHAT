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





# ---------------- Gupshup WhatsApp Helper ----------------
def send_whatsapp_message(to_number, text):
    """
    Send WhatsApp message via Gupshup API.
    """
    api_key = os.getenv("GUPSHUP_API_KEY")
    app_name = os.getenv("GUPSHUP_APP_NAME")
    source = os.getenv("GUPSHUP_SOURCE")   # sender number
    if not api_key or not app_name or not source:
        print("⚠️ Gupshup API not configured properly.")
        return False

    url = "https://api.gupshup.io/sm/api/v1/msg"
    headers = {
        "apikey": api_key,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "channel": "whatsapp",
        "source": source,
        "destination": to_number,
        "message": text,
        "src.name": app_name
    }
    try:
        r = requests.post(url, data=payload, headers=headers, timeout=10)
        print("📩 Gupshup WhatsApp sent:", r.text)
        return True
    except Exception as e:
        print("❌ Gupshup send failed:", e)
        return False




def finalize(uid,c):
    e=CLASS_ATT[uid]; cls,sec=e["class"],e["sec"]; marks=e["marks"]; 
    studs=students_ws.get_all_records(); studs=[s for s in studs if s["Class"]==cls and s["Section"]==sec]; d=today_str()
    ws=ensure_att_tab(d,cls,sec)
    absentees=[]
    for s in studs:
        rid=str(s["RollNo"]); name=s["Name"]; mark=marks.get(rid,"Present")
        ws.append_row([rid,s.get("RegID",""),name,mark,uid,now_ts()])
        attendance_ws.append_row([d,cls,sec,rid,name,mark,"",uid])
        if mark=="Absent": absentees.append({"RegID":s.get("RegID",""),"StudentName":name,"ParentChatId":s.get("ParentChatId","")})
    notify_parents(absentees,d,cls,sec,uid)
    CLASS_ATT.pop(uid,None)
    bot.answer_callback_query(c.id,"Submitted"); bot.send_message(c.message.chat.id,"✅ Attendance submitted")











