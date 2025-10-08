def get_cached_online_master_list():
    if _is_cache_fresh("online_master"):
        return _cache["online_master"][0]
    try:
        data = online_master_sheet.get_all_records()
        _cache["online_master"] = (data, time.time())
        return data
    except Exception as e:
        print("⚠️ Error fetching online master list:", e)
        return _cache["online_master"][0] or []

def get_cached_online_attendance_rows():
    if _is_cache_fresh("online_attendance_rows"):
        return _cache["online_attendance_rows"][0]
    try:
        rows = online_attendance_sheet.get_all_records()
        _cache["online_attendance_rows"] = (rows, time.time())
        return rows
    except Exception as e:
        print("⚠️ Error fetching online attendance rows:", e)
        return _cache["online_attendance_rows"][0] or []
