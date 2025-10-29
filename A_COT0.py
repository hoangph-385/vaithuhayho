# -*- coding: utf-8 -*-
import os
import sys
import json
import base64
import io
import pandas as pd
import unicodedata
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict
import time

# ───── Import utility ─────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utility import (
    build_api_headers,
    firebase_read_cookie_rtdb,
    firebase_url,
    seatalk_send_group_message_rtdb,
    seatalk_send_file_group_message_rtdb,
    payload_file_group_message,
)

# ─────────── Cấu hình ───────────
sys.stdout.reconfigure(encoding="utf-8")

WHS = ["VNDB", "VNDL"]
GROUP_ID = "NTU1MDE4MzQwMDU4"
TOKEN_NAME = "Token_XX"

API_CREATE_TASK = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/create_export_task"
# Không gắn sẵn pageno/count để tránh trùng tham số khi phân trang
API_SEARCH_TASK = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/search_export_task?is_myself=1"
API_FILTER_ORDER = "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/salesorder/search_wave_filter_order"

EXPORT_MODULE = 2
TASK_TYPE = 701

POLL_STEP = 3      # giây
MAX_WAIT  = 120    # giây
DL_TIMEOUT = 60    # giây

# Cho phép lọc theo nhiều Lane; để [] để tắt lọc lane khi test
ALLOWED_LANES = ["L-VN11"]   # ví dụ: ["L-VN11", "L-VN12"]; [] = không lọc lane (khuyên để [] khi kiểm thử)

TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh

# ─────────── Time range: D-2 00:00:00 → D0 23:59:59 ───────────
def calc_time_range_seconds() -> Tuple[int, int]:
    now = datetime.now(TZ)
    d0_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d2_start = d0_start - timedelta(days=2)
    d0_end   = d0_start + timedelta(days=1) - timedelta(seconds=1)
    return int(d2_start.timestamp()), int(d0_end.timestamp())

# ─────────── Helpers ───────────
def _status_breakdown(headers: dict, order_no_list: List[str]) -> Dict[str, int]:
    """
    Lấy phân loại trạng thái như file INTRA cũ:
    1 -> Normal, 2 -> OOS_Picking, 3 -> OOS_WHS
    Trả về số nguyên (0 nếu không có), có chia batch để tránh payload quá dài.
    """
    def _fetch_total(oos_type: int, batch: List[str]) -> int:
        pl = {
            "order_no_list": batch,
            "order_filter_type": 0,
            "order_oos_type": oos_type,
            "pageno": 1,
            "count": 1,
            "is_get_total": 1,
        }
        r = requests.post(API_FILTER_ORDER, json=pl, headers=headers, timeout=30)
        r.raise_for_status()
        rj = r.json() or {}
        total = ((rj.get("data") or {}).get("total")) or 0
        try:
            return int(total)
        except Exception:
            return 0

    def _sum(oos_type: int) -> int:
        if not order_no_list:
            return 0
        total = 0
        for i in range(0, len(order_no_list), 100):
            total += _fetch_total(oos_type, order_no_list[i:i+100])
        return total

    return {"normal": _sum(1), "oos_picking": _sum(2), "oos_whs": _sum(3)}

def _norm_text(s: pd.Series) -> pd.Series:
    # Tránh chuỗi 'nan'/'None' sau astype(str)
    s = s.astype(str).str.strip()
    return s.replace({"nan": "", "None": "", "NaT": ""}, regex=False)

def _norm_vn_name(s: pd.Series) -> pd.Series:
    s = s.astype(str).fillna("").str.strip().str.lower()
    s = s.apply(lambda v: "".join(
        c for c in unicodedata.normalize("NFD", v)
        if unicodedata.category(c) != "Mn"
    ))
    s = s.str.replace("đ", "d")
    s = s.str.replace(r"[-_/]", " ", regex=True)
    s = s.str.replace(r"\b(tp|thanh pho|city|province|tinh|quan|huyen)\b", " ", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return s

def _is_dn(series: pd.Series) -> pd.Series:
    k = _norm_vn_name(series)
    return k.str.contains(r"\bda\s*nang\b|\bdanang\b", regex=True, na=False)

def _is_hue(series: pd.Series) -> pd.Series:
    k = _norm_vn_name(series)
    return k.str.contains(r"\bhue\b|\bthua\s*thien\s*hue\b", regex=True, na=False)

def _is_qnam(series: pd.Series) -> pd.Series:
    k = _norm_vn_name(series)
    return k.str.contains(r"\bquang\s*nam\b", regex=True, na=False)

def _download_with_retry(url: str, headers: dict, timeout: int = DL_TIMEOUT, retries: int = 3, backoff: float = 1.5) -> bytes:
    last_err = None
    for i in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(backoff ** (i - 1))
    raise last_err or Exception(f"Failed to download after {retries} retries")

def _search_tasks_pages(headers: dict, pages: int = 5, count: int = 100) -> list:
    """
    Gộp nhiều trang kết quả search_export_task để tránh 'trôi trang'.
    Trả về list các task (dict).
    """
    all_tasks = []
    # Chuẩn hóa base URL, đảm bảo không có pageno/count trùng lặp
    base = API_SEARCH_TASK if "pageno=" not in API_SEARCH_TASK else API_SEARCH_TASK.split("?")[0] + "?is_myself=1"
    for p in range(1, pages + 1):
        url = f"{base}&pageno={p}&count={count}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            rj = r.json() or {}
            if rj.get("retcode", 0) != 0:
                raise RuntimeError(f"search_export_task retcode={rj.get('retcode')}")
            tasks = (rj.get("data") or {}).get("list") or []
            if not tasks:
                break
            all_tasks.extend(tasks)
        except Exception as e:
            print(f"⚠️ Poll page {p} error: {e}")
            time.sleep(1)
    return all_tasks

def _create_and_fetch_excel(headers: dict, time_from: int, time_to: int, wh: str) -> pd.DataFrame:
    created_ts_s  = int(time.time())
    created_ts_ms = int(time.time() * 1000)

    extra_data = {
        "timeRange": 0,
        "module": EXPORT_MODULE,
        "taskType": TASK_TYPE,
        "status_list": [0],
        "order_type": 0,
        "include_sku_list": 1,
        "date_ref": 0,
        "time_from": time_from,
        "time_to": time_to,
    }
    payload = {
        "export_module": EXPORT_MODULE,
        "task_type": TASK_TYPE,
        "extra_data": json.dumps(extra_data, separators=(",", ":")),
    }

    r = requests.post(API_CREATE_TASK, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    resp = r.json()
    if resp.get("retcode") != 0:
        raise RuntimeError(f"Create task failed: {resp}")

    task_id = (resp.get("data") or {}).get("task_id") or resp.get("task_id")
    print(f"[{wh}] 🆕 Created task_id={task_id}")

    time.sleep(2)

    deadline = time.time() + MAX_WAIT
    last_perc, download_link = -1, None

    def _normalize_ctime_to_s(ctime_val) -> int:
        try:
            c = int(ctime_val)
            return c // 1000 if c > 1_000_000_000_000 else c
        except:
            return 0

    while time.time() < deadline and not download_link:
        try:
            tasks = _search_tasks_pages(headers, pages=5, count=100)
        except Exception as e:
            print(f"[{wh}] ⚠️ Poll error: {e}")
            time.sleep(POLL_STEP)
            continue

        found = None
        if task_id:
            for t in tasks:
                if str(t.get("task_id")) == str(task_id):
                    found = t
                    break

        if not found:
            window_s = 120
            candidates = []
            for t in tasks:
                if t.get("export_module") == EXPORT_MODULE and t.get("task_type") == TASK_TYPE:
                    ctime_s = _normalize_ctime_to_s(t.get("ctime", 0))
                    if abs(ctime_s - created_ts_s) <= window_s or abs((t.get("ctime", 0) or 0) - created_ts_ms) <= window_s * 1000:
                        candidates.append((ctime_s, t))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                found = candidates[0][1]

        if found:
            perc = int(found.get("processed_percentage") or 0)
            if perc != last_perc:
                print(f"[{wh}] ⏳ Task {found.get('task_id')} xử lý: {perc}%")
                last_perc = perc
            dl = found.get("download_link")
            if perc >= 100 and dl:
                download_link = dl
                break
        else:
            sample = tasks[:5]
            dbg = [
                {
                    "task_id": t.get("task_id"),
                    "module": t.get("export_module"),
                    "type": t.get("task_type"),
                    "ctime_s": _normalize_ctime_to_s(t.get("ctime")),
                    "perc": t.get("processed_percentage"),
                }
                for t in sample
            ]
            print(f"[{wh}] ⏳ Chưa thấy task tương ứng. (top-5)", dbg)

        time.sleep(POLL_STEP)

    if not download_link:
        raise TimeoutError("Report chưa sẵn sàng trong thời gian chờ.")

    file_bytes = _download_with_retry(download_link, headers=headers, timeout=DL_TIMEOUT, retries=3)
    # Ép dtype=str để ổn định
    return pd.read_excel(io.BytesIO(file_bytes), dtype=str, engine="openpyxl")

def _filter_and_unique(df: pd.DataFrame, wh: str) -> List[str]:
    need_cols = ["Buyer State", "Lane Code", "WMS Order No"]
    missing = [c for c in need_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Thiếu cột bắt buộc: {missing}")

    buyer_state = _norm_text(df["Buyer State"])
    lane_code   = _norm_text(df["Lane Code"]).str.upper()
    wms_no      = _norm_text(df["WMS Order No"])

    # masks theo tỉnh
    mask_dn   = _is_dn(buyer_state)
    mask_hue  = _is_hue(buyer_state)
    mask_qnam = _is_qnam(buyer_state)
    mask_state = mask_dn | mask_hue | mask_qnam
    # mask_state = mask_dn | mask_qnam


    # lane filter (giữ như bạn đang dùng; hoặc để [] để test)
    if 'ALLOWED_LANES' in globals() and ALLOWED_LANES:
        allowed = set(s.upper() for s in ALLOWED_LANES)
        mask_lane = lane_code.isin(allowed)
    else:
        mask_lane = pd.Series(True, index=df.index)

    # ---- UNIQUE breakdown theo tỉnh: PRE-LANE
    # u_dn_pre   = wms_no[mask_dn   & wms_no.ne("")].drop_duplicates().size
    # u_hue_pre  = wms_no[mask_hue  & wms_no.ne("")].drop_duplicates().size
    # u_qn_pre   = wms_no[mask_qnam & wms_no.ne("")].drop_duplicates().size
    # u_any_pre  = wms_no[mask_state & wms_no.ne("")].drop_duplicates().size
    # print(f"[{wh}] State breakdown (unique, PRE-lane): "
    #       f"{{'da_nang': {u_dn_pre}, 'hue': {u_hue_pre}, 'quang_nam': {u_qn_pre}, 'any': {u_any_pre}}}")

    # ---- UNIQUE breakdown theo tỉnh: POST-LANE
    u_dn_post   = wms_no[mask_dn   & mask_lane & wms_no.ne("")].drop_duplicates().size
    u_hue_post  = wms_no[mask_hue  & mask_lane & wms_no.ne("")].drop_duplicates().size
    u_qn_post   = wms_no[mask_qnam & mask_lane & wms_no.ne("")].drop_duplicates().size
    print(f"[{wh}] State breakdown (unique): "
          f"{{'da_nang': {u_dn_post}, 'hue': {u_hue_post}, 'quang_nam': {u_qn_post}}}")

    # Thông tin lane
    # print(f"[{wh}] Lane true (rows): {int(mask_lane.sum())}")

    # Trả list unique theo điều kiện cuối cùng
    filtered = wms_no[mask_state & mask_lane & wms_no.ne("")]
    uniq_list = list(dict.fromkeys(filtered.tolist()))
    # print(f"[{wh}] [DEBUG] unique wms_list count = {len(uniq_list)}")
    return uniq_list

def _run_for_wh(wh: str, time_from: int, time_to: int) -> Tuple[str, List[str], str, dict]:
    try:
        cookie = firebase_read_cookie_rtdb(wh, firebase_url)
        headers = build_api_headers(cookie)

        df = _create_and_fetch_excel(headers, time_from, time_to, wh)  # ← thêm wh

        wms_list = _filter_and_unique(df, wh=wh)
        # print(f"[DEBUG] unique wms_list count = {len(wms_list)}")

        # breakdown trạng thái (không ảnh hưởng output nếu lỗi)
        status = {}
        try:
            status = _status_breakdown(headers, wms_list)
            print(f"[{wh}] → Normal: {status['normal']} | OOS_Picking: {status['oos_picking']} | OOS_WHS: {status['oos_whs']}")
        except Exception as se:
            print(f"⚠️ [{wh}] Lỗi lấy trạng thái filter_order: {type(se).__name__}: {se}")

        return wh, wms_list, "", status
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"❌ {wh} lỗi: {err}")
        return wh, [], err, {}

# ─────────── MAIN ───────────
def main():
    time_from, time_to = calc_time_range_seconds()

    # Log khung thời gian
    dfrom = datetime.fromtimestamp(time_from, TZ).strftime("%Y-%m-%d %H:%M:%S")
    dto   = datetime.fromtimestamp(time_to, TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"⏱️ Range: {dfrom} → {dto} (GMT+7)")

    results: Dict[str, List[str]] = {}
    errors: Dict[str, str] = {}
    statuses: Dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=len(WHS)) as exe:
        futs = {exe.submit(_run_for_wh, wh, time_from, time_to): wh for wh in WHS}
        for fut in as_completed(futs):
            wh = futs[fut]
            try:
                w, lst, err, stat = fut.result()
                results[w] = lst
                if err:
                    errors[w] = err
                statuses[w] = stat
            except Exception as e:
                # Không để văng luồng
                print(f"❌ {wh} gặp lỗi ngoài dự kiến: {e}")
                results[wh] = []
                errors[wh] = f"UnexpectedError: {e}"

    # ── Tổng hợp & gửi SeaTalk theo format yêu cầu ──
    vndb_list = results.get("VNDB", [])
    vndl_list = results.get("VNDL", [])
    total = len(vndb_list) + len(vndl_list)

    def _fmt_line(wh: str, cnt: int, st: dict) -> str:
        # thêm 1 khoảng trắng trước dấu ']' như bạn demo: [VNDB = 120 ]
        return (f"**[{wh} = {cnt}]** → "
                f"Normal: {st.get('normal', 0)} | "
                f"OOS_Picking: {st.get('oos_picking', 0)} | "
                f"OOS_WHS: {st.get('oos_whs', 0)}")

    msg_lines = [f"**TOTAL_COT0 (DNG-35/36/37) = {total}**"]

    # ghép theo thứ tự VNDB rồi VNDL
    msg_lines.append(_fmt_line("VNDB", len(vndb_list), statuses.get("VNDB", {})))
    msg_lines.append(_fmt_line("VNDL", len(vndl_list), statuses.get("VNDL", {})))

    message = "\n".join(msg_lines)
    seatalk_send_group_message_rtdb(GROUP_ID, message, TOKEN_NAME)

    # ── Xuất CSV 2 cột: VNDB | VNDL ──
    def _col(v, i): return v[i] if i < len(v) else ""
    max_len = max(len(vndb_list), len(vndl_list))
    rows = [{"VNDB": _col(vndb_list, i), "VNDL": _col(vndl_list, i)} for i in range(max_len)]
    df_out = pd.DataFrame(rows, columns=["VNDB", "VNDL"])

    buf = io.BytesIO()
    df_out.to_csv(buf, index=False, encoding="utf-8-sig")
    buf.seek(0)
    file_b64 = base64.b64encode(buf.read()).decode("utf-8")
    filename = f"LIST_COT0_{total}.csv"

    payload = payload_file_group_message(GROUP_ID, filename, file_b64)
    res = seatalk_send_file_group_message_rtdb(payload, TOKEN_NAME)
    print("SeaTalk file send result:", res)

if __name__ == "__main__":
    main()
