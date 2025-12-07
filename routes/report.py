import os
import sys
import requests
import math
import csv
import io
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, url_for, send_file

from utils.firebase import rtdb
from utils.timeutils import today_short
from utils.report import build_report_message, create_excel_report
from utils.seatalk import seatalk_text, seatalk_file
from config import BASE_DIR

# Import utility functions from parent directory for LH functionality
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
UTILITY_ROOT = os.path.dirname(PROJECT_ROOT)
if UTILITY_ROOT not in sys.path:
    sys.path.insert(0, UTILITY_ROOT)

try:
    from utility import build_api_headers, firebase_read_cookie_rtdb, firebase_url, get_daily_timestamps, convert_timestamp_to_day_time_gmt7
    UTILITY_AVAILABLE = True
except ImportError:
    UTILITY_AVAILABLE = False
    # Fallback implementations if utility module is not available
    def build_api_headers(cookie=None):
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def get_daily_timestamps():
        now = datetime.now(timezone(timedelta(hours=7)))
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return int(start_of_day.timestamp()), int(end_of_day.timestamp())

    def convert_timestamp_to_day_time_gmt7(timestamp):
        if not timestamp:
            return ""
        dt = datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=7)))
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def firebase_read_cookie_rtdb(wh, url):
        return ""

    firebase_url = ""

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


@bp.get("/LH_report")
def api_lh_report():
    """
    Get all LH (Last Hub) trips from SPX API
    Based on LH.py functionality

    Query params:
        date: Optional date in YYYY-MM-DD format (default: today)

    Returns:
        JSON with list of trips including:
        - id, trip_number, operator
        - seal_time, loading_time
        - load_quantity, vehicle_number, vehicle_type_name
    """
    WH = "SPX"

    # Get date parameter (default to today)
    date_param = request.args.get('date', '')

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get cookie: {str(e)}"
        }), 500

    headers = build_api_headers(cookie)

    # Get daily timestamps
    try:
        if date_param:
            # Parse date string (YYYY-MM-DD) and convert to timestamps
            target_date = datetime.strptime(date_param, "%Y-%m-%d")
            gmt7 = timezone(timedelta(hours=7))
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=gmt7)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=gmt7)
            from_time = int(start_of_day.timestamp())
            to_time = int(end_of_day.timestamp())
        else:
            from_time, to_time = get_daily_timestamps()
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "Invalid date format. Use YYYY-MM-DD"
        }), 400
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get timestamps: {str(e)}"
        }), 500

    # Build API URL
    url = f"https://spx.shopee.vn/api/admin/transportation/trip/history/list?loading_time={from_time},{to_time}&pageno=1&count=100&mtime={from_time},{to_time}&query_type=2&middle_station=3983"

    # Call API
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") == 0 and data.get("data"):
            trips = []
            for trip in data["data"]["list"]:
                # Ưu tiên lấy station 2259 trước
                station = next((s for s in trip.get("trip_station", []) if s.get("station") == 2259), {})

                trips.append({
                    "id": trip["id"],
                    "trip_number": trip["trip_number"],
                    "driver_name": trip.get("driver_name", ""),
                    "seal_time": convert_timestamp_to_day_time_gmt7(station.get("seal_time")) if station.get("seal_time") else "",
                    "loading_time": convert_timestamp_to_day_time_gmt7(station.get("loading_time")) if station.get("loading_time") else "",
                    "sequence_number": station.get("sequence_number", 1),
                    "load_quantity": station.get("load_quantity", 0),
                    "to_parcel_quantity": 0,  # Will be fetched by frontend using Promise.all
                    "vehicle_number": trip.get("vehicle_number", ""),
                    "vehicle_type_name": trip.get("vehicle_type_name", ""),
                })

            return jsonify({
                "ok": True,
                "total_trips": len(trips),
                "trips": trips,
                "from_time": from_time,
                "to_time": to_time
            })
        else:
            return jsonify({
                "ok": False,
                "error": data.get("message", "Unknown error from API"),
                "retcode": data.get("retcode")
            }), 400

    except requests.exceptions.Timeout:
        return jsonify({
            "ok": False,
            "error": "API request timeout"
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "ok": False,
            "error": f"API request failed: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


@bp.get("/LH_report_handover")
def api_lh_report_handover():

    WH = "SPX"

    # Get date parameter (default to today)
    date_param = request.args.get('date', '')

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get cookie: {str(e)}"
        }), 500

    headers = build_api_headers(cookie)

    # Get daily timestamps
    try:
        if date_param:
            # Parse date string (YYYY-MM-DD) and convert to timestamps
            target_date = datetime.strptime(date_param, "%Y-%m-%d")
            gmt7 = timezone(timedelta(hours=7))
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=gmt7)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=gmt7)
            from_time = int(start_of_day.timestamp())
            to_time = int(end_of_day.timestamp())
        else:
            from_time, to_time = get_daily_timestamps()
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "Invalid date format. Use YYYY-MM-DD"
        }), 400
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get timestamps: {str(e)}"
        }), 500


    url = f"https://spx.shopee.vn/api/admin/transportation/trip/list?loading_time={from_time},{to_time}&pageno=1&count=100&mtime={from_time},{to_time}&query_type=2&middle_station=3983"

    # Call API
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") == 0 and data.get("data"):
            trips = []
            for trip in data["data"]["list"]:
                # Ưu tiên lấy station 2259 trước
                station = next((s for s in trip.get("trip_station", []) if s.get("station") == 2259), {})

                # Nếu không có station 2259, lấy station đầu tiên
                if not station and trip.get("trip_station"):
                    station = trip["trip_station"][0] if isinstance(trip["trip_station"], list) else {}

                trips.append({
                    "id": trip["id"],
                    "trip_number": trip["trip_number"],
                    "driver_name": trip.get("driver_name", ""),
                    "seal_time": convert_timestamp_to_day_time_gmt7(station.get("seal_time")) if station.get("seal_time") else "",
                    "loading_time": convert_timestamp_to_day_time_gmt7(station.get("loading_time")) if station.get("loading_time") else "",
                    "sequence_number": station.get("sequence_number", 1),
                    "load_quantity": station.get("load_quantity", 0),
                    "to_parcel_quantity": 0,  # Will be fetched by frontend using Promise.all
                    "vehicle_number": trip.get("vehicle_number", ""),
                    "vehicle_type_name": trip.get("vehicle_type_name", ""),
                })

            return jsonify({
                "ok": True,
                "total_trips": len(trips),
                "trips": trips,
                "from_time": from_time,
                "to_time": to_time
            })
        else:
            return jsonify({
                "ok": False,
                "error": data.get("message", "Unknown error from API"),
                "retcode": data.get("retcode")
            }), 400

    except requests.exceptions.Timeout:
        return jsonify({
            "ok": False,
            "error": "API request timeout"
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "ok": False,
            "error": f"API request failed: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


@bp.get("/LH_get_parcel_count/<trip_id>")
def api_lh_get_parcel_count(trip_id):
    WH = "SPX"

    # Get sequence_number and kind (default outbound) from query params
    sequence_number = request.args.get('seq', 1, type=int)
    kind = request.args.get('kind', 'outbound').lower()
    if kind not in ("outbound", "handover"):
        return jsonify({"ok": False, "error": "Invalid kind. Use outbound or handover"}), 400

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get cookie: {str(e)}"
        }), 500

    headers = build_api_headers(cookie)

    # Choose API based on kind: handover uses current loading, outbound uses history
    base_url = "https://spx.shopee.vn/api/admin/transportation/trip/loading/list" if kind == "handover" else "https://spx.shopee.vn/api/admin/transportation/trip/history/loading/list"

    try:
        params = {
            "trip_id": trip_id,
            "pageno": 1,
            "count": 50,  # Only need first page to get total_parcel
            "loaded_sequence_number": sequence_number,
            "type": "outbound"
        }

        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") != 0:
            return jsonify({
                "ok": False,
                "error": data.get("message", "Unknown error from API")
            }), 400

        total_parcel = data["data"].get("total_parcel", 0)

        return jsonify({
            "ok": True,
            "trip_id": trip_id,
            "total_parcel": total_parcel
        })

    except requests.exceptions.Timeout:
        return jsonify({
            "ok": False,
            "error": "API request timeout"
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "ok": False,
            "error": f"API request failed: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


@bp.get("/LH_get_list/<trip_id>/<trip_number>")
def api_lh_get_list(trip_id, trip_number):
    WH = "SPX"

    # Get sequence_number and kind from query params (kind defaults to outbound)
    sequence_number = request.args.get('seq', 1, type=int)
    kind = request.args.get('kind', 'outbound').lower()
    if kind not in ("outbound", "handover"):
        return jsonify({"ok": False, "error": "Invalid kind. Use outbound or handover"}), 400

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to get cookie: {str(e)}"
        }), 500

    headers = build_api_headers(cookie)

    # Select API: handover uses current loading list; outbound uses history loading list
    base_url = "https://spx.shopee.vn/api/admin/transportation/trip/loading/list" if kind == "handover" else "https://spx.shopee.vn/api/admin/transportation/trip/history/loading/list"

    try:
        # First request to get total count
        params = {
            "trip_id": trip_id,
            "pageno": 1,
            "count": 50,
            "loaded_sequence_number": sequence_number,
            "type": "outbound"
        }

        response = requests.get(base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") != 0:
            return jsonify({
                "ok": False,
                "error": data.get("message", "Unknown error from API")
            }), 400

        # Get pagination info
        total = data["data"]["total"]
        count = data["data"]["count"]
        total_parcel = data["data"].get("total_parcel", 0)
        total_pages = math.ceil(total / count)

        # Collect all data
        all_data = []

        # Add data from first page
        for item in data["data"]["list"]:
            to_number = item.get("to_number", "")
            pack_type_name = item.get("pack_type_name", "")
            to_parcel_quantity = item.get("to_parcel_quantity", 0)
            scan_number = item.get("scan_number", "")
            operator = item.get("operator", "")
            to_weight = round(item.get("to_weight", 0) / 1000, 3)
            ctime = item.get("ctime", 0)

            # Nếu to_parcel_quantity > 1, gọi API để lấy fleet_order_id và ghi từng dòng
            if to_parcel_quantity > 1:
                try:
                    detail_url = "https://spx.shopee.vn/api/in-station/general_to/detail/search"
                    detail_params = {
                        "to_number": to_number,
                        "pageno": 1,
                        "count": 300
                    }
                    detail_resp = requests.get(detail_url, params=detail_params, headers=headers, timeout=30)
                    detail_resp.raise_for_status()
                    detail_json = detail_resp.json()
                    if detail_json.get("retcode") == 0:
                        lst = detail_json.get("data", {}).get("list", [])
                        fleet_ids = [row.get("fleet_order_id", "") for row in lst if row.get("fleet_order_id")]
                        # Ghi mỗi fleet_order_id thành 1 dòng riêng
                        if fleet_ids:
                            for fleet_id in fleet_ids:
                                all_data.append({
                                    "to_number": to_number,
                                    "pack_type_name": pack_type_name,
                                    "scan_number": fleet_id,
                                    "operator": operator,
                                    "to_weight": to_weight,
                                    "ctime": ctime
                                })
                        else:
                            # Không có fleet_id, ghi dòng gốc
                            all_data.append({
                                "to_number": to_number,
                                "pack_type_name": pack_type_name,
                                "scan_number": scan_number,
                                "operator": operator,
                                "to_weight": to_weight,
                                "ctime": ctime
                            })
                except Exception:
                    # Giữ nguyên dòng gốc nếu có lỗi
                    all_data.append({
                        "to_number": to_number,
                        "pack_type_name": pack_type_name,
                        "scan_number": scan_number,
                        "operator": operator,
                        "to_weight": to_weight,
                        "ctime": ctime
                    })
            else:
                # to_parcel_quantity <= 1, pack_type_name = "Single"
                all_data.append({
                    "to_number": to_number,
                    "pack_type_name": "Single",
                    "scan_number": scan_number,
                    "operator": operator,
                    "to_weight": to_weight,
                    "ctime": ctime
                })

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            params["pageno"] = page
            response = requests.get(base_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("retcode") != 0:
                continue

            for item in data["data"]["list"]:
                to_number = item.get("to_number", "")
                pack_type_name = item.get("pack_type_name", "")
                to_parcel_quantity = item.get("to_parcel_quantity", 0)
                scan_number = item.get("scan_number", "")
                operator = item.get("operator", "")
                to_weight = round(item.get("to_weight", 0) / 1000, 2)
                ctime = item.get("ctime", 0)

                # Nếu to_parcel_quantity > 1, gọi API để lấy fleet_order_id và ghi từng dòng
                if to_parcel_quantity > 1:
                    try:
                        detail_url = "https://spx.shopee.vn/api/in-station/general_to/detail/search"
                        detail_params = {
                            "to_number": to_number,
                            "pageno": 1,
                            "count": 300
                        }
                        detail_resp = requests.get(detail_url, params=detail_params, headers=headers, timeout=30)
                        detail_resp.raise_for_status()
                        detail_json = detail_resp.json()
                        if detail_json.get("retcode") == 0:
                            lst = detail_json.get("data", {}).get("list", [])
                            fleet_ids = [row.get("fleet_order_id", "") for row in lst if row.get("fleet_order_id")]
                            # Ghi mỗi fleet_order_id thành 1 dòng riêng
                            if fleet_ids:
                                for fleet_id in fleet_ids:
                                    all_data.append({
                                        "to_number": to_number,
                                        "pack_type_name": pack_type_name,
                                        "scan_number": fleet_id,
                                        "operator": operator,
                                        "to_weight": to_weight,
                                        "ctime": ctime
                                    })
                            else:
                                # Không có fleet_id, ghi dòng gốc
                                all_data.append({
                                    "to_number": to_number,
                                    "pack_type_name": pack_type_name,
                                    "scan_number": scan_number,
                                    "operator": operator,
                                    "to_weight": to_weight,
                                    "ctime": ctime
                                })
                    except Exception:
                        # Giữ nguyên dòng gốc nếu có lỗi
                        all_data.append({
                            "to_number": to_number,
                            "pack_type_name": pack_type_name,
                            "scan_number": scan_number,
                            "operator": operator,
                            "to_weight": to_weight,
                            "ctime": ctime
                        })
                else:
                    # to_parcel_quantity <= 1, pack_type_name = "Single"
                    all_data.append({
                        "to_number": to_number,
                        "pack_type_name": "Single",
                        "scan_number": scan_number,
                        "operator": operator,
                        "to_weight": to_weight,
                        "ctime": ctime
                    })

        # Sort data by: ctime -> pack_type_name
        all_data.sort(key=lambda x: (x["ctime"], x["pack_type_name"]))

        # Convert ctime to GMT+7
        gmt7 = timezone(timedelta(hours=7))
        for item in all_data:
            if item["ctime"] > 0:
                dt = datetime.fromtimestamp(item["ctime"], tz=timezone.utc)
                dt_gmt7 = dt.astimezone(gmt7)
                item["ctime"] = dt_gmt7.strftime("%Y-%m-%d %H:%M:%S")
            else:
                item["ctime"] = ""

        # Create CSV in memory
        output = io.StringIO()
        fieldnames = ['to_number', 'pack_type_name', 'scan_number', 'operator', 'to_weight', 'ctime']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_data)

        # Convert to bytes for download
        csv_bytes = io.BytesIO()
        csv_bytes.write(output.getvalue().encode('utf-8-sig'))
        csv_bytes.seek(0)

        # Prefer FE-supplied counts (what user sees) for filename; fall back to API totals
        fe_to_qty = request.args.get('to_qty', type=int)
        fe_parcel_qty = request.args.get('parcel_qty', type=int)
        filename_to = fe_to_qty if fe_to_qty is not None else total
        filename_parcel = fe_parcel_qty if fe_parcel_qty is not None else total_parcel
        # Short name to align with Excel tab: <trip>_<TO>_<PARCEL>.csv
        filename = f"{trip_number}_{filename_to}_{filename_parcel}.csv"

        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except requests.exceptions.Timeout:
        return jsonify({
            "ok": False,
            "error": "API request timeout"
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "ok": False,
            "error": f"API request failed: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500


@bp.get("/LH_run_sheet/<trip_id>")
def api_lh_run_sheet(trip_id):
    """Fetch run sheet URL for a trip, prioritize station_id=2259 by default."""
    WH = "SPX"

    station_id = request.args.get('station_id', 2259, type=int)

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to get cookie: {str(e)}"}), 500

    headers = build_api_headers(cookie)

    url = "https://spx.shopee.vn/api/admin/transportation/run_sheet/list"

    try:
        resp = requests.get(url, params={"trip_id": trip_id}, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retcode") != 0:
            return jsonify({"ok": False, "error": data.get("message", "API error"), "retcode": data.get("retcode")}), 400

        sheets = data.get("data", {}).get("list", []) or []

        # Prefer matching station_id with sheet_url present
        sheet = next((s for s in sheets if s.get("station_id") == station_id and s.get("sheet_url")), None)
        if not sheet:
            sheet = next((s for s in sheets if s.get("sheet_url")), None)

        if not sheet or not sheet.get("sheet_url"):
            return jsonify({"ok": False, "error": "No sheet_url found"}), 404

        sheet_url = sheet.get("sheet_url", "")
        download_url = f"https://spx.shopee.vn{sheet_url}" if sheet_url.startswith('/') else sheet_url

        return jsonify({
            "ok": True,
            "download_url": download_url,
            "sheet_url": sheet_url,
            "station_id": sheet.get("station_id"),
            "station_name": sheet.get("station_name"),
            "sequence_number": sheet.get("sequence_number")
        })

    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "API request timeout"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"ok": False, "error": f"API request failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": f"Unexpected error: {str(e)}"}), 500


@bp.get("/LH_download_pdf/<trip_id>")
def api_lh_download_pdf(trip_id):
    """Proxy PDF download to avoid CORS issues. Fetches sheet URL then streams PDF."""
    WH = "SPX"

    station_id = request.args.get('station_id', 2259, type=int)

    # Get cookie from Firebase RTDB
    try:
        cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to get cookie: {str(e)}"}), 500

    headers = build_api_headers(cookie)

    url = "https://spx.shopee.vn/api/admin/transportation/run_sheet/list"

    try:
        # First, get the sheet URL
        resp = requests.get(url, params={"trip_id": trip_id}, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retcode") != 0:
            return jsonify({"ok": False, "error": data.get("message", "API error")}), 400

        sheets = data.get("data", {}).get("list", []) or []

        # Prefer matching station_id with sheet_url present
        sheet = next((s for s in sheets if s.get("station_id") == station_id and s.get("sheet_url")), None)
        if not sheet:
            sheet = next((s for s in sheets if s.get("sheet_url")), None)

        if not sheet or not sheet.get("sheet_url"):
            return jsonify({"ok": False, "error": "No sheet_url found"}), 404

        sheet_url = sheet.get("sheet_url", "")
        download_url = f"https://spx.shopee.vn{sheet_url}" if sheet_url.startswith('/') else sheet_url

        # Now fetch the PDF and stream it
        pdf_resp = requests.get(download_url, headers=headers, timeout=30, stream=True)
        pdf_resp.raise_for_status()

        # Extract filename from URL or use default
        filename = download_url.split('/')[-1] if '/' in download_url else f"trip_{trip_id}.pdf"
        if not filename.endswith('.pdf'):
            filename = f"{filename}.pdf"

        # Stream the PDF back to client
        pdf_bytes = io.BytesIO(pdf_resp.content)
        pdf_bytes.seek(0)

        return send_file(
            pdf_bytes,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "API request timeout"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"ok": False, "error": f"API request failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": f"Unexpected error: {str(e)}"}), 500
