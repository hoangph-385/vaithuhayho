# -*- coding: utf-8 -*-
"""
SDD Tool Backend API
Based on A_COT0.py functionality for DNG-35/36/37 order analysis
"""

import os
import sys
import json
import base64
import io
import pandas as pd
import unicodedata
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import List, Tuple, Dict
import time
from flask import Blueprint, request, jsonify, Response, abort
from werkzeug.exceptions import ClientDisconnected

# Import utility functions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
UTILITY_ROOT = os.path.dirname(PROJECT_ROOT)  # Go up one more level to find utility.py
if UTILITY_ROOT not in sys.path:
    sys.path.insert(0, UTILITY_ROOT)

try:
    from utility import (
        build_api_headers,
        firebase_read_cookie_rtdb,
        firebase_url,
        seatalk_send_group_message_rtdb,
        seatalk_send_file_group_message_rtdb,
        payload_file_group_message,
    )
    UTILITY_AVAILABLE = True
except ImportError:
    print("Warning: utility module not found, some features will be disabled")
    UTILITY_AVAILABLE = False

bp = Blueprint("sdd", __name__)

# Configuration
WHS = ["VNDB", "VNDL"]
GROUP_ID = "NTU1MDE4MzQwMDU4"
TOKEN_NAME = "Token_XX"

API_CREATE_TASK = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/create_export_task"
API_SEARCH_TASK = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/search_export_task?is_myself=1"
API_FILTER_ORDER = "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/salesorder/search_wave_filter_order"

EXPORT_MODULE = 2
TASK_TYPE = 701

POLL_STEP = 3      # seconds
MAX_WAIT = 120     # seconds
DL_TIMEOUT = 60    # seconds

TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh

# Helper functions (copied from A_COT0.py)
def _status_breakdown(headers: dict, order_no_list: List[str]) -> Dict[str, int]:
    """Get status breakdown: 1 -> Normal, 2 -> OOS_Picking, 3 -> OOS_WHS"""
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
    """Fetch multiple pages of export tasks"""
    all_tasks = []
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
    """Create export task and fetch Excel data"""
    created_ts_s = int(time.time())
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
                print(f"[{wh}] ⏳ Task {found.get('task_id')} processing: {perc}%")
                last_perc = perc
            dl = found.get("download_link")
            if perc >= 100 and dl:
                # CRITICAL: Wait for file to be fully written after 100%
                print(f"[{wh}] ✅ Task complete, waiting for file stabilization...")
                time.sleep(3)  # Give server time to finalize the file
                download_link = dl
                break

        time.sleep(POLL_STEP)

    if not download_link:
        raise TimeoutError("Report not ready within timeout")

    print(f"[{wh}] 📥 Downloading Excel file...")
    file_bytes = _download_with_retry(download_link, headers=headers, timeout=DL_TIMEOUT, retries=3)

    print(f"[{wh}] 📊 Reading Excel data...")
    return pd.read_excel(io.BytesIO(file_bytes), dtype=str, engine="openpyxl")

def _filter_and_process_orders(df: pd.DataFrame, wh: str, lane_filter: str = "L-VN11") -> List[dict]:
    """Filter orders and return detailed order list"""
    need_cols = ["Buyer State", "Lane Code", "WMS Order No"]
    missing = [c for c in need_cols if c not in df.columns]
    if missing:
        available = list(df.columns)[:10]  # Show first 10 columns for debugging
        raise KeyError(f"Missing required columns: {missing}. Available columns: {available}")

    buyer_state = _norm_text(df["Buyer State"])
    lane_code = _norm_text(df["Lane Code"]).str.upper()
    wms_no = _norm_text(df["WMS Order No"])

    # Region filters
    mask_dn = _is_dn(buyer_state)
    mask_hue = _is_hue(buyer_state)
    mask_qnam = _is_qnam(buyer_state)
    mask_state = mask_dn | mask_hue | mask_qnam

    # Lane filter - default to L-VN11 if not provided
    if not lane_filter:
        lane_filter = "L-VN11"

    allowed_lanes = [s.strip().upper() for s in lane_filter.split(",")]
    mask_lane = lane_code.isin(allowed_lanes)

    # Apply filters
    filtered_mask = mask_state & mask_lane & wms_no.ne("")
    filtered_df = df[filtered_mask]

    # Create order list with normalized WMS order numbers and details
    # Use the previously computed `wms_no` Series (normalized) so uniqueness
    # later is reliable and not affected by whitespace or formatting differences.
    orders = []
    for idx, row in filtered_df.iterrows():
        # Prefer the normalized value from wms_no Series; fallback to raw cell
        norm_wms = wms_no.loc[idx] if idx in wms_no.index else str(row.get("WMS Order No", "")).strip()
        orders.append({
            "wms_order_no": norm_wms,
            "buyer_state": str(row.get("Buyer State", "")).strip(),
            "lane_code": str(row.get("Lane Code", "")).strip(),
            "warehouse": wh,
            "status": "Normal",
            # keep raw value for debugging if needed
            "raw_wms_order_no": row.get("WMS Order No", "")
        })

    return orders

def _run_for_wh(wh: str, time_from: int, time_to: int, lane_filter: str = "L-VN11") -> Tuple[str, List[dict], str, dict]:
    """Process data for a single warehouse"""
    try:
        if not UTILITY_AVAILABLE:
            # For testing without utility module
            return wh, [], "utility module not available", {}

        cookie = firebase_read_cookie_rtdb(wh, firebase_url)
        headers = build_api_headers(cookie)

        df = _create_and_fetch_excel(headers, time_from, time_to, wh)
        orders = _filter_and_process_orders(df, wh, lane_filter)

        # Deduplicate orders by normalized WMS Order No while preserving order.
        # This ensures FE won't see duplicates and total counts are correct.
        seen = set()
        unique_orders = []
        for o in orders:
            key = str(o.get("wms_order_no", "")).strip()
            if not key:
                # skip empty keys
                continue
            if key in seen:
                continue
            seen.add(key)
            unique_orders.append(o)
        orders = unique_orders

        # Get unique order numbers for status breakdown
        wms_list = [order["wms_order_no"] for order in orders]
        unique_wms_list = list(dict.fromkeys(wms_list))

        # Get status breakdown
        status = {}
        try:
            status = _status_breakdown(headers, unique_wms_list)
            print(f"[{wh}] → Normal: {status['normal']} | OOS_Picking: {status['oos_picking']} | OOS_WHS: {status['oos_whs']}")
        except Exception as se:
            print(f"⚠️ [{wh}] Status breakdown error: {type(se).__name__}: {se}")

        return wh, orders, "", status
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"❌ {wh} error: {err}")
        return wh, [], err, {}

# API Routes
@bp.route("/sdd", methods=["POST"])
def api_sdd_fetch():
    """Fetch SDD data for both warehouses"""
    import uuid
    req_id = str(uuid.uuid4())[:8]
    try:
        req = request.get_json(force=True) or {}
        time_from = req.get("time_from")
        time_to = req.get("time_to")
        lane_filter = req.get("lane_filter", "L-VN11").strip()
        if not lane_filter:
            lane_filter = "L-VN11"

        if not time_from or not time_to:
            return jsonify({"error": "time_from and time_to are required"}), 400

        # Log time range
        dfrom = datetime.fromtimestamp(time_from, TZ).strftime("%Y-%m-%d %H:%M:%S")
        dto = datetime.fromtimestamp(time_to, TZ).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{req_id}] ⏱️ SDD Range: {dfrom} → {dto} (GMT+7)")

        results = {}
        errors = {}
        statuses = {}

        # Use timeout to prevent long-running tasks from holding resources
        # if FE disconnects. Default 300s (5 min) for full export + processing.
        timeout_sec = 300
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(WHS)) as exe:
            futs = {exe.submit(_run_for_wh, wh, time_from, time_to, lane_filter): wh for wh in WHS}
            try:
                for fut in as_completed(futs, timeout=timeout_sec):
                    wh = futs[fut]
                    try:
                        w, orders, err, stat = fut.result(timeout=5)
                        results[w] = orders
                        if err:
                            errors[w] = err
                        statuses[w] = stat
                        print(f"[{req_id}] ✓ {w}: {len(orders)} orders collected")
                    except FuturesTimeoutError:
                        print(f"[{req_id}] ⚠️ {wh} task timeout (5s)")
                        results[wh] = []
                        errors[wh] = "Task timeout"
                    except Exception as e:
                        print(f"[{req_id}] ❌ {wh} unexpected error: {e}")
                        results[wh] = []
                        errors[wh] = f"UnexpectedError: {e}"
            except FuturesTimeoutError:
                print(f"[{req_id}] ⚠️ Executor timeout (300s), returning partial results")
            except ClientDisconnected:
                print(f"[{req_id}] ⚠️ Client disconnected mid-fetch, aborting")
                return jsonify({"error": "Client disconnected", "partial": results, "request_id": req_id}), 499
            except Exception as e:
                print(f"[{req_id}] ❌ Executor error: {e}")
                return jsonify({"error": f"Execution error: {e}", "request_id": req_id}), 500

        vndb_orders = results.get("VNDB", [])
        vndl_orders = results.get("VNDL", [])

        # Safety: dedupe again at API layer per-warehouse to avoid any FE duplicates
        # in case upstream logic or FE mixing reintroduces duplicates.
        def _dedupe_orders(orders_list: List[dict]) -> List[dict]:
            seen_local = set()
            out = []
            for o in orders_list:
                k = str(o.get("wms_order_no", "")).strip()
                if not k or k in seen_local:
                    continue
                seen_local.add(k)
                out.append(o)
            return out

        before_vndb, before_vndl = len(vndb_orders), len(vndl_orders)
        vndb_orders = _dedupe_orders(vndb_orders)
        vndl_orders = _dedupe_orders(vndl_orders)
        after_vndb, after_vndl = len(vndb_orders), len(vndl_orders)
        if before_vndb != after_vndb or before_vndl != after_vndl:
            print(f"[{req_id}] [SDD] Dedupe applied at API layer: VNDB {before_vndb}->{after_vndb}, VNDL {before_vndl}->{after_vndl}")
        # Keep legacy total as sum per-warehouse (backward compatible)
        total_orders = len(vndb_orders) + len(vndl_orders)

        # Also compute a global unique total across both warehouses by wms_order_no
        # to avoid double counting if the same order appears in both datasets.
        seen_all = set()
        for o in (vndb_orders + vndl_orders):
            k = str(o.get("wms_order_no", "")).strip()
            if k:
                seen_all.add(k)
        total_unique_orders = len(seen_all)

        response = {
            "success": True,
            "vndb_orders": vndb_orders,
            "vndl_orders": vndl_orders,
            "total_orders": total_orders,
            "total_unique_orders": total_unique_orders,
            "stats": {
                "vndb": statuses.get("VNDB", {}),
                "vndl": statuses.get("VNDL", {})
            },
            "errors": errors,
            "time_range": {
                "from": dfrom,
                "to": dto
            }
        }

        elapsed = time.time() - start_time
        print(f"[{req_id}] ✓ Complete in {elapsed:.2f}s, returning {total_orders} orders ({total_unique_orders} unique)")
        return jsonify(response)

    except Exception as e:
        print(f"[{req_id}] ❌ SDD API error: {e}")
        return jsonify({"error": str(e)}), 500
