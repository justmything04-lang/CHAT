    # after finishing absentee sheets + parent notifications
    off_abs = len(absentees)
    on_abs = len(absentees_online)
    off_present = len(present_ids)
    on_present = len(present_online_ids)

    public = (
        f"📊 Attendance Report for {today}\n\n"
        f"📍 Offline: ✅ {off_present} / ❌ {off_abs}\n"
        f"🌐 Online:  ✅ {on_present} / ❌ {on_abs}"
    )
    _post_public(public)   # <-- no links for the topic

    return off_abs, on_abs, off_present, on_present
