import requests
import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utility import build_api_headers, firebase_read_cookie_rtdb, firebase_url, get_daily_timestamps, convert_timestamp_to_day_time_gmt7

WH = "SPX"
cookie = firebase_read_cookie_rtdb(WH, firebase_url)
headers = build_api_headers(cookie)

def get_all_trips():
    """
    Lấy danh sách tất cả các trip từ API

    Returns:
        List các trip hoặc None nếu lỗi
    """
    from_time, to_time = get_daily_timestamps()
    url = f"https://spx.shopee.vn/api/admin/transportation/trip/history/list?loading_time={from_time},{to_time}&pageno=1&count=24&mtime={from_time},{to_time}&middle_station=3983"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data.get("retcode") == 0 and data.get("data"):
            trips = []
            for trip in data["data"]["list"]:
                station = next((s for s in trip.get("trip_station", []) if s.get("sequence_number") == 1), {})
                # Lấy thông tin station 2259
                station_2259 = next((s for s in trip.get("trip_station", []) if s.get("station") == 2259), {})

                trips.append({
                    "id": trip["id"],
                    "trip_number": trip["trip_number"],
                    "operator": trip.get("operator", ""),
                    "seal_time": convert_timestamp_to_day_time_gmt7(station.get("seal_time")) if station.get("seal_time") else "",
                    "loading_time": convert_timestamp_to_day_time_gmt7(station.get("loading_time")) if station.get("loading_time") else "",
                    "load_quantity": station_2259.get("load_quantity", 0),
                    "vehicle_number": trip.get("vehicle_number", ""),
                    "vehicle_type_name": trip.get("vehicle_type_name", ""),
                })
            return trips
        else:
            print(f"❌ API trả về lỗi: {data.get('message', 'Unknown error')}")
            return None

    except Exception as e:
        print(f"❌ Lỗi khi lấy danh sách trip: {e}")
        return None

def get_trip_id_by_number(trip_number, trips):
    """
    Tìm trip_id từ trip_number trong danh sách trips

    Args:
        trip_number: Số trip cần tìm
        trips: Danh sách các trip

    Returns:
        trip_id nếu tìm thấy, None nếu không tìm thấy
    """
    for trip in trips:
        if trip["trip_number"] == trip_number:
            return trip["id"]

    print(f"❌ Không tìm thấy trip_number: {trip_number}")
    return None

def main():
    """
    Main function: hiển thị danh sách trip, nhập trip_number, chuyển đổi thành trip_id và chạy GET_LIST.py
    """
    while True:
        print("=" * 60)
        print("TRIP DATA EXPORT TOOL")
        print("=" * 60)

        # Lấy danh sách trips
        print("\n📋 Đang lấy danh sách trips...")
        trips = get_all_trips()

        if not trips:
            print("❌ Không thể lấy danh sách trips!")
            return

        # Hiển thị danh sách trips
        print(f"\n✓ Tìm thấy {len(trips)} trips:\n")
        print(f"{'STT':<5} {'Trip Number':<18} {'Vehicle':<15} {'Type':<12} {'Load':<6} {'Operator':<25} {'Seal Time':<20}")
        print("-" * 120)

        for i, trip in enumerate(trips, 1):
            print(f"{i:<5} {trip['trip_number']:<18} {trip['vehicle_number']:<15} {trip['vehicle_type_name']:<12} {trip['load_quantity']:<6} {trip['operator']:<25} {trip['seal_time']:<20}")

        print("\n" + "=" * 60)

        # Nhập trip_number
        trip_number = input("\nNhập trip_number (hoặc 'END' để thoát): ").strip()

        if trip_number.upper() == 'END':
            print("👋 Thoát chương trình.")
            break

        if not trip_number:
            print("⚠️ Vui lòng nhập trip_number hoặc 'END' để thoát.\n")
            continue

        print(f"\n🔍 Đang tìm trip_id cho trip_number: {trip_number}...")

        # Lấy trip_id từ trip_number
        trip_id = get_trip_id_by_number(trip_number, trips)

        if trip_id:
            print(f"✓ Tìm thấy trip_id: {trip_id}")
            print(f"\n📊 Đang xuất dữ liệu...")

            # Chạy GET_LIST.py với trip_id và trip_number
            get_list_path = os.path.join(SCRIPT_DIR, "GET_LIST.py")

            try:
                result = subprocess.run(
                    [sys.executable, get_list_path, str(trip_id), trip_number],
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )

                # In output từ GET_LIST.py
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)

                if result.returncode == 0:
                    print("\n✓ Hoàn tất!")
                else:
                    print(f"\n❌ Lỗi khi chạy GET_LIST.py (exit code: {result.returncode})")

            except Exception as e:
                print(f"❌ Lỗi khi chạy GET_LIST.py: {e}")
        else:
            print("\n❌ Không thể tiếp tục do không tìm thấy trip_id")

        print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main()
