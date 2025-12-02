import requests, json
import os, sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from utility import build_api_headers, firebase_read_cookie_rtdb, firebase_url, get_daily_timestamps, convert_timestamp_to_day_time_gmt7

WH = "SPX"
from_time, to_time = get_daily_timestamps()
URL = f"https://spx.shopee.vn/api/admin/transportation/trip/history/list?loading_time={from_time},{to_time}&pageno=1&count=24&mtime={from_time},{to_time}&middle_station=3983"

# Lấy cookie từ Firebase
cookie = firebase_read_cookie_rtdb(WH, firebase_url)
headers = build_api_headers(cookie)

def extract_trip_data(trip):
    station = next((s for s in trip.get("trip_station", []) if s.get("sequence_number") == 1), {})
    return {
        "id": trip["id"],
        "trip_number": trip["trip_number"],
        "operator": trip["operator"],
        "seal_time": convert_timestamp_to_day_time_gmt7(station.get("seal_time")) if station.get("seal_time") else None,
        "loading_time": convert_timestamp_to_day_time_gmt7(station.get("loading_time")) if station.get("loading_time") else None,
    }

response = requests.get(URL, headers=headers)
try:
    if response.status_code == 200:
        data = response.json()
        if data.get("retcode") == 0 and data.get("data"):
            results = [extract_trip_data(trip) for trip in data["data"]["list"]]
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"❌ API trả về lỗi: {data.get('message', 'Unknown error')}")
    else:
        print(f"❌ HTTP Status: {response.status_code}")
except Exception as e:
    print(f"❌ Lỗi: {e}")


