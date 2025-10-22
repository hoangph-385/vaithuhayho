import os
from flask import Blueprint, request, jsonify, url_for

from utils.firebase import rtdb
from utils.timeutils import today_short
from utils.report import build_report_message, create_excel_report
from utils.seatalk import seatalk_text, seatalk_file
from config import BASE_DIR

bp = Blueprint("report", __name__)

@bp.post("/run")
def api_report_run():
    """Generate Excel report and send via SeaTalk (text + file)."""
    req = request.get_json(force=True) or {}
    date_str = req.get("date") or today_short()

    # Fetch snapshot from RTDB
    snap = rtdb.reference(f"/{date_str}/DATA_SCAN").get() or {}

    # Build message and filename
    msg, filename, per_ch_non_cancel, total_cancel, total_non_cancel = build_report_message(date_str, snap)

    # Create Excel bytes and save a copy to static/reports for browser download
    excel_bytes = create_excel_report(snap, filename)
    reports_dir = os.path.join(BASE_DIR, "static", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    filepath = os.path.join(reports_dir, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(excel_bytes)
    except Exception:
        # If saving fails, we still attempt to send via SeaTalk
        pass

    public_url = url_for("static", filename=f"reports/{filename}", _external=True)

    # Send to SeaTalk: text + file
    st_text_res = None
    st_file_res = None
    st_err = None
    try:
        st_text_res = seatalk_text(msg)
    except Exception as e:
        st_err = f"seatalk_text: {e}"
    try:
        caption = f"Báo cáo Handover ngày {date_str} – tổng {total_non_cancel} đơn\n{public_url}"
        st_file_res = seatalk_file(excel_bytes, filename, caption=caption)
    except Exception as e:
        st_err = (st_err + "; " if st_err else "") + f"seatalk_file: {e}"

    return jsonify({
        "ok": True,
        "file_url": public_url,
        "filename": filename,
        "counters": {
            "per_channel_non_cancel": per_ch_non_cancel,
            "total_cancel": total_cancel,
            "total_non_cancel": total_non_cancel
        },
        "seatalk": {
            "text": st_text_res or {"ok": False},
            "file": st_file_res or {"ok": False},
            "file_url": public_url,
            "error": st_err
        }
    })
