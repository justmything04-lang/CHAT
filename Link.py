# ---- Google Sheets Read Throttle & Retry (to avoid 429) ----
_last_gs_read = [0.0]
GS_READ_MIN_GAP = float(os.getenv("GS_READ_MIN_GAP", "0.35"))  # seconds between reads
GS_READ_MAX_RETRIES = int(os.getenv("GS_READ_MAX_RETRIES", "3"))

def _gs_pause():
    import time as _t
    gap = GS_READ_MIN_GAP - (_t.time() - _last_gs_read[0])
    if gap > 0:
        _t.sleep(gap)
    _last_gs_read[0] = _t.time()

def _gs_read(callable_fn):
    """Throttle + retry wrapper for gspread reads like ws.get_all_records()."""
    import time as _t
    for attempt in range(1, GS_READ_MAX_RETRIES + 1):
        _gs_pause()
        try:
            return callable_fn()
        except gspread.exceptions.APIError as e:
            s = str(e)
            if "429" in s or "Rate Limit Exceeded" in s:
                # exponential backoff
                _t.sleep(min(2.0 * attempt, 6.0))
                continue
            raise
for _, ds, ws in day_tabs:
    try:
        rows = _gs_read(lambda: ws.get_all_records())
        for a in rows:
