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
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utility import build_api_headers, firebase_read_cookie_rtdb, firebase_url

WH = "SPX"
cookie = firebase_read_cookie_rtdb(WH, firebase_url)
headers = build_api_headers(cookie)

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
        "count": 50,
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
            all_data.append({
                "to_number": item.get("to_number", ""),
                "to_parcel_quantity": item.get("to_parcel_quantity", 0),
                "pack_type_name": item.get("pack_type_name", ""),
                "scan_number": item.get("scan_number", ""),
                "operator": item.get("operator", ""),
                "to_weight": round(item.get("to_weight", 0) / 1000, 3),
                "ctime": item.get("ctime", 0)
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
                all_data.append({
                    "to_number": item.get("to_number", ""),
                    "to_parcel_quantity": item.get("to_parcel_quantity", 0),
                    "pack_type_name": item.get("pack_type_name", ""),
                    "scan_number": item.get("scan_number", ""),
                    "operator": item.get("operator", ""),
                    "to_weight": round(item.get("to_weight", 0) / 1000, 2),
                    "ctime": item.get("ctime", 0)
                })

        # Sắp xếp dữ liệu theo: ctime -> to_parcel_quantity -> pack_type_name
        all_data.sort(key=lambda x: (x["ctime"], x["to_parcel_quantity"], x["pack_type_name"]))

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
            fieldnames = ['to_number', 'to_parcel_quantity', 'pack_type_name', 'scan_number', 'operator', 'to_weight', 'ctime']
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
    # Nhập trip_id từ người dùng hoặc sử dụng giá trị mặc định
    trip_number = None
    if len(sys.argv) > 1:
        trip_id = sys.argv[1]
        if len(sys.argv) > 2:
            trip_number = sys.argv[2]
    else:
        trip_id = input("Nhập trip_id: ").strip()

    if trip_id:
        get_trip_data(trip_id, trip_number)
    else:
        print("Vui lòng nhập trip_id!")
