def _write_biweekly_sheet(win_start, win_end, off_rows, on_rows):
    """
    Writes/updates 'BiWeekly_Summary' in main workbook with sort & colours.
    Columns: Mode, RegID, Name, Present, Absent, Percent, Band, WindowStart, WindowEnd, CreatedAt
    Returns: worksheet gid (ws.id) or None on error.
    """
    try:
        wb = client.open_by_key(SHEET_ID)
        try:
            ws = wb.worksheet("BiWeekly_Summary")
        except gspread.exceptions.WorksheetNotFound:
            ws = wb.add_worksheet(title="BiWeekly_Summary", rows="2000", cols="10")
            ws.update("A1:J1", [[
                "Mode","RegID","Name","Present","Absent","Percent","Band",
                "WindowStart","WindowEnd","CreatedAt"
            ]])
            if set_frozen:
                try:
                    set_frozen(ws, rows=1)
                except Exception:
                    pass

        off_sorted = _sorted_by_band(off_rows)
        on_sorted  = _sorted_by_band(on_rows)

        def _fmt(mode, r):
            rid, name, pres, absd, pct, band = r
            return [mode, rid, name, pres, absd, round(pct*100,1), band, str(win_start), str(win_end), now_ts()]

        rows_to_write = [_fmt("Offline", r) for r in off_sorted] + [_fmt("Online", r) for r in on_sorted]
        if rows_to_write:
            ws.append_rows(rows_to_write, value_input_option='USER_ENTERED')

        # Colour by band (optional if gspread_formatting available)
        if format_cell_ranges and Color and CellFormat:
            try:
                vals = ws.get_all_records()
                colors = {
                    "Low":     Color(1, 0.8, 0.8),   # light red
                    "Average": Color(1, 1, 0.8),     # light yellow
                    "High":    Color(0.85, 1, 0.85), # light green
                    "100%":    Color(0.85, 0.90, 1)  # light blue
                }
                fmt_cache = {k: CellFormat(backgroundColor=v, textFormat=TextFormat(bold=False)) for k, v in colors.items()}
                for i, rec in enumerate(vals, start=2):
                    band = rec.get("Band","")
                    if band in fmt_cache:
                        try:
                            format_cell_ranges(ws, [(f"A{i}:J{i}", fmt_cache[band])])
                        except Exception:
                            pass
            except Exception as e:
                print("Colouring skipped:", e)

        return ws.id  # ✅ return gid so caller can build link
    except Exception as e:
        print("⚠️ BiWeekly sheet write error:", e)
        return None
