import requests
import csv
import math
import os
import sys
from datetime import datetime, timezone, timedelta

# Fix UTF-8 encoding cho Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
UTILITY_ROOT = os.path.dirname(PROJECT_ROOT)
if UTILITY_ROOT not in sys.path:
    sys.path.insert(0, UTILITY_ROOT)

try:
    from utility import build_api_headers, firebase_read_cookie_rtdb, firebase_url
    UTILITY_AVAILABLE = True
except ImportError:
    UTILITY_AVAILABLE = False
    # Fallback implementations
    def build_api_headers(cookie=None):
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def firebase_read_cookie_rtdb(wh, url):
        return ""

    firebase_url = ""

WH = "SPX"
cookie = firebase_read_cookie_rtdb(WH, firebase_url) if UTILITY_AVAILABLE else ""
headers = build_api_headers(cookie)

def get_trip_id_from_trip_number(trip_number):
    """
    Tìm trip_id từ trip_number

    Args:
        trip_number: Trip number cần tìm

    Returns:
        trip_id nếu tìm thấy, None nếu không tìm thấy
    """
    try:
        # Lấy timestamp cho hôm nay
        now = datetime.now(timezone(timedelta(hours=7)))
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        from_time = int(start_of_day.timestamp())
        to_time = int(end_of_day.timestamp())

        url = f"https://spx.shopee.vn/api/admin/transportation/trip/history/list?loading_time={from_time},{to_time}&pageno=1&count=300&mtime={from_time},{to_time}&middle_station=3983"

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") == 0 and data.get("data"):
            for trip in data["data"]["list"]:
                if trip.get("trip_number") == trip_number:
                    return trip.get("id")

        print(f"Không tìm thấy trip_number: {trip_number}")
        return None

    except Exception as e:
        print(f"Lỗi khi tìm trip_id: {e}")
        return None

def get_trip_data(trip_id, trip_number=None):
    """
    Lấy dữ liệu trip từ API với pagination và xuất ra file CSV

    Args:
        trip_id: ID của trip cần lấy dữ liệu
        trip_number: Trip number (tùy chọn, dùng để đặt tên file)
    """
    # Bước 1: Lấy sequence_number từ trip history
    trip_history_url = "https://spx.shopee.vn/api/admin/transportation/trip/history/list"
    trip_params = {
        "trip_id": trip_id,
        "type": "outbound"
    }

    print(f"Đang lấy thông tin trip_id: {trip_id}...")

    try:
        trip_response = requests.get(trip_history_url, params=trip_params, headers=headers)
        trip_response.raise_for_status()
        trip_data = trip_response.json()

        if trip_data.get("retcode") != 0:
            print(f"Lỗi API trip history: {trip_data.get('message')}")
            return

        # Debug: In ra cấu trúc dữ liệu
        print(f"DEBUG - trip_data keys: {trip_data.keys()}")
        if "data" in trip_data:
            print(f"DEBUG - data keys: {trip_data['data'].keys()}")
            if "list" in trip_data["data"] and len(trip_data["data"]["list"]) > 0:
                print(f"DEBUG - trip_station: {trip_data['data']['list'][0].get('trip_station', [])}")

        # Lấy sequence_number từ trip_station (ưu tiên station 2259)
        sequence_number = 1  # Giá trị mặc định
        if "data" in trip_data:
            # Lấy trip đầu tiên từ list
            if "list" in trip_data["data"] and len(trip_data["data"]["list"]) > 0:
                trip = trip_data["data"]["list"][0]
                trip_station = trip.get("trip_station", [])

                if isinstance(trip_station, list) and len(trip_station) > 0:
                    # Tìm station 2259 trước
                    station_2259 = next((s for s in trip_station if s.get("station") == 2259), None)
                    if station_2259:
                        sequence_number = station_2259.get("sequence_number", 1)
                    else:
                        # Fallback lấy phần tử đầu tiên
                        sequence_number = trip_station[0].get("sequence_number", 1)

        print(f"Sequence number: {sequence_number}")

    except requests.exceptions.RequestException as e:
        print(f"Lỗi kết nối API trip history: {e}")
        print("Sử dụng sequence_number mặc định = 1")
    except Exception as e:
        print(f"Lỗi lấy sequence_number: {e}")
        print("Sử dụng sequence_number mặc định = 1")


    # Bước 2: Lấy danh sách loading với sequence_number đã lấy được
    base_url = "https://spx.shopee.vn/api/admin/transportation/trip/history/loading/list"

    # Lấy trang đầu tiên để biết tổng số trang
    params = {
        "trip_id": trip_id,
        "pageno": 1,
        "count": 300,
        "loaded_sequence_number": sequence_number,
        "type": "outbound"
    }

    print(f"Đang lấy dữ liệu loading list...")

    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") != 0:
            print(f"Lỗi API: {data.get('message')}")
            return

        # Lấy thông tin pagination
        total = data["data"]["total"]
        count = data["data"]["count"]
        total_parcel = data["data"]["total_parcel"]

        # Tính số trang
        total_pages = math.ceil(total / count)
        print(f"Tổng số TO: {total}, Tổng số parcel: {total_parcel}, Số trang: {total_pages}")

        # Thu thập tất cả dữ liệu
        all_data = []

        # Thêm dữ liệu từ trang đầu tiên
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
                    detail_resp = requests.get(detail_url, params=detail_params, headers=headers)
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
                except Exception as e:
                    # Giữ nguyên dòng gốc nếu có lỗi
                    print(f"Lỗi khi lấy chi tiết TO {to_number}: {e}")
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

        # Lấy dữ liệu từ các trang còn lại
        for page in range(2, total_pages + 1):
            print(f"Đang lấy trang {page}/{total_pages}...")
            params["pageno"] = page

            response = requests.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("retcode") != 0:
                print(f"Lỗi API tại trang {page}: {data.get('message')}")
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
                        detail_resp = requests.get(detail_url, params=detail_params, headers=headers)
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
                    except Exception as e:
                        # Giữ nguyên dòng gốc nếu có lỗi
                        print(f"Lỗi khi lấy chi tiết TO {to_number}: {e}")
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

        # Sắp xếp dữ liệu theo: ctime -> pack_type_name
        all_data.sort(key=lambda x: (x["ctime"], x["pack_type_name"]))

        # Convert ctime sang GMT+7
        gmt7 = timezone(timedelta(hours=7))
        for item in all_data:
            if item["ctime"] > 0:
                dt = datetime.fromtimestamp(item["ctime"], tz=timezone.utc)
                dt_gmt7 = dt.astimezone(gmt7)
                item["ctime"] = dt_gmt7.strftime("%Y-%m-%d %H:%M:%S")
            else:
                item["ctime"] = ""

        # Tạo tên file CSV
        if trip_number:
            filename = f"{trip_number}_TO-{total}_PARCEL-{total_parcel}.csv"
        else:
            filename = f"{trip_id}_TO-{total}_PARCEL-{total_parcel}.csv"

        # Xuất ra file CSV
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['to_number', 'pack_type_name', 'scan_number', 'operator', 'to_weight', 'ctime']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            writer.writerows(all_data)

        print(f"✓ Đã xuất {len(all_data)} dòng dữ liệu ra file: {filename}")
        return filename

    except requests.exceptions.RequestException as e:
        print(f"Lỗi kết nối API: {e}")
    except Exception as e:
        print(f"Lỗi: {e}")

if __name__ == "__main__":
    # Nhập trip_id hoặc trip_number từ người dùng
    input_value = None
    trip_number = None

    if len(sys.argv) > 1:
        input_value = sys.argv[1]
        if len(sys.argv) > 2:
            trip_number = sys.argv[2]
    else:
        input_value = input("Nhập trip_id hoặc trip_number: ").strip()

    if not input_value:
        print("Vui lòng nhập trip_id hoặc trip_number!")
        sys.exit(1)

    # Kiểm tra xem input là trip_id (số) hay trip_number (chuỗi)
    if input_value.isdigit():
        # Là trip_id
        trip_id = input_value
    else:
        # Là trip_number - cần tìm trip_id
        print(f"Đang tìm trip_id cho trip_number: {input_value}...")
        trip_id = get_trip_id_from_trip_number(input_value)
        if not trip_id:
            print("Không thể tìm thấy trip_id!")
            sys.exit(1)
        trip_number = input_value
        print(f"✓ Tìm thấy trip_id: {trip_id}")

    get_trip_data(trip_id, trip_number)
