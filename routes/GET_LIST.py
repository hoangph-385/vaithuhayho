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
    base_url = "https://spx.shopee.vn/api/admin/transportation/trip/history/loading/list"

    # Lấy trang đầu tiên để biết tổng số trang
    params = {
        "trip_id": trip_id,
        "pageno": 1,
        "count": 50,
        "loaded_sequence_number": 1,
        "type": "outbound"
    }

    print(f"Đang lấy dữ liệu cho trip_id: {trip_id}...")

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

        # Sắp xếp dữ liệu theo: to_parcel_quantity -> pack_type_name -> ctime
        all_data.sort(key=lambda x: (x["to_parcel_quantity"], x["pack_type_name"], x["ctime"]))

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
