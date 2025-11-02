# routes/wms.py - FIXED VERSION WITH TIMEOUT & DISCONNECT HANDLING
# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import ClientDisconnected
import requests, json, urllib.request, uuid, traceback
from urllib.parse import urlparse
import re, html as htmllib
import os, sys, time

# ==== import utility (dùng header chuẩn đã chạy OK ở script cũ) ====
def build_api_headers(cookie: str | None = None):
    """Tạo headers chuẩn cho API requests"""
    headers = {
    "content-type": "application/json",
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://wms.ssc.shopee.vn/",
    "Sec-CH-UA": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": "\"Windows\"",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers

bp = Blueprint("wms", __name__)

URL_SCAN = "https://wms.ssc.shopee.vn/api/v2/apps/labor/staffrecord/record_attendance"
URL_TASK = "https://wms.ssc.shopee.vn/api/v2/apps/labor/staffrecord/record_activity"
VANHANH_BASE = "https://vanhanh.shopee.vn"

# ===================== Logging helpers =====================
def _reqid():
    return request.headers.get("X-Req-Id") or str(uuid.uuid4())[:8]

def _log(msg, **kw):
    rid = _reqid()
    current_app.logger.info(f"[{rid}] {msg} " + (f"{kw}" if kw else ""))

def _warn(msg, **kw):
    rid = _reqid()
    current_app.logger.warning(f"[{rid}] {msg} " + (f"{kw}" if kw else ""))

def _errlog(msg, **kw):
    rid = _reqid()
    current_app.logger.error(f"[{rid}] {msg} " + (f"{kw}" if kw else ""))

# ===================== Common helpers =====================
def _ok(data):     return jsonify({"retcode": 0, "data": data})
def _err(code,msg):return jsonify({"retcode": code, "message": msg}), 400

def get_cookie_from_rtdb(warehouse: str) -> str:
    """
    Lấy cookie WMS từ RTDB public.
    """
    url = f"https://cookie-vnw-default-rtdb.firebaseio.com/{warehouse}/value/cookie.json"
    with urllib.request.urlopen(url, timeout=10) as f:
        return json.loads(f.read().decode())

def _to_vendor_code(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith(("http://", "https://")):
        try:
            p = urlparse(s)
            parts = [x for x in p.path.split("/") if x]
            return parts[-1] if parts else ""
        except:
            pass
    if "/" in s:
        parts = [x for x in s.split("/") if x]
        return parts[-1] if parts else ""
    return s

def _pick_staff_no_from_info(j: dict) -> str:
    cand_keys = [
        "vacc_number", "vac_number",
        "wfm", "WFM",
        "staffNo", "staff_no",
        "employeeCode", "employee_code",
        "id", "code"
    ]
    pools = [j]
    for k in ("all_info","info","info_staff"):
        if isinstance(j.get(k), dict):
            pools.append(j[k])
    for d in pools:
        if isinstance(d, dict):
            for k in cand_keys:
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return ""

def _vanhanh_info_url(vendor_code: str) -> str:
    return f"{VANHANH_BASE}/spx-ops/wh/{vendor_code}"

def _extract_next_data(html_text: str):
    if not isinstance(html_text, str) or not html_text:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, flags=re.S|re.I)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        try:
            unescaped = htmllib.unescape(raw)
            return json.loads(unescaped)
        except Exception:
            return None

# ===================== Health / Probe =====================
@bp.get("/_probe_login")
def probe_login():
    wh = (request.args.get("wh") or "VNDB").strip()
    try:
        cookie = get_cookie_from_rtdb(wh)
    except Exception as ex:
        return jsonify({"retcode": 500, "message": f"cookie load error: {ex}"}), 500

    headers = build_api_headers(cookie)

    day0 = int(time.time()) - 86400
    day1 = int(time.time())
    url = f"https://wms.ssc.shopee.vn/api/v2/apps/dashboard/labor/dsstaff/search_staff_tracking?from_time={day0}&to_time={day1}&pageno=1&count=1"

    try:
        r = requests.get(url, headers=headers, timeout=20)
        preview = (r.text or "")[:200]
    except Exception as ex:
        return jsonify({"retcode": 502, "message": f"probe upstream error: {ex}"}), 502

    try:
        j = r.json()
    except Exception:
        j = None

    return jsonify({"retcode": 0, "status": r.status_code, "json": j, "preview": preview}), 200

@bp.get("/_ping")
def ping():
    return _ok({"pong": True})

@bp.get("/_cookie_check")
def cookie_check():
    wh = (request.args.get("wh") or "VNDB").strip()
    try:
        cookie = get_cookie_from_rtdb(wh)
        ok = bool(cookie and len(cookie) > 10)
        return _ok({"warehouse": wh, "has_cookie": ok, "len": len(cookie or "")})
    except Exception as ex:
        return jsonify({"retcode": 500, "message": f"cookie error: {ex}"}), 500

# ===================== INFO (vanhanh) =====================
@bp.get("/info/<vendor_code>")
def info_staff_get(vendor_code):
    vendor_code = _to_vendor_code(vendor_code)
    if not vendor_code:
        return _err(400, "vendor_code trống")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json"
    }
    url = _vanhanh_info_url(vendor_code)
    _log("INFO start", url=url, vendor_code=vendor_code)

    try:
        r = requests.get(url, headers=headers, timeout=20)
    except Exception as ex:
        _errlog("INFO upstream exception", error=str(ex))
        return jsonify({"retcode": 500, "message": f"vanhanh error: {ex}"}), 502

    ctype = (r.headers.get("content-type") or "").lower()
    is_json = "application/json" in ctype
    body_preview = r.text[:200].replace("\n", " ")

    if r.status_code != 200:
        return jsonify({"retcode": r.status_code,
                        "message": f"vanhanh {r.status_code}: {body_preview}"}), r.status_code

    data_all_info, profile_image_url, full_name, contractor = {}, "", "", ""

    if is_json:
        try:
            j = r.json()
        except Exception:
            j = {}
        data_all_info = j.get("all_info", {}) if isinstance(j, dict) else {}
        profile_image_url = j.get("profile_image_url") or ""
        full_name = j.get("full_name") or j.get("name") or ""
        contractor = j.get("contractor") or j.get("vendor") or ""
    else:
        next_data = _extract_next_data(r.text)
        if not next_data:
            _warn("INFO no __NEXT_DATA__ found")
            return jsonify({
                "ok": True,
                "all_info": {},
                "full_name": "",
                "contractor": "",
                "profile_image_url": "",
                "staff_id": vendor_code,
                "wfm": ""
            })
        pp = (next_data.get("props", {}) or {}).get("pageProps", {}) or {}
        data_all_info = pp.get("all_info", {}) or {}
        profile_image_url = pp.get("profile_image_url") or ""
        full_name = data_all_info.get("full_name") or pp.get("full_name") or ""
        contractor = data_all_info.get("contractor") or pp.get("contractor") or ""

    result = {
        "ok": True,
        "all_info": data_all_info,
        "full_name": full_name,
        "contractor": contractor,
        "profile_image_url": profile_image_url,
        "staff_id": vendor_code,
    }

    staff_no = (data_all_info.get("vacc_number")
                or data_all_info.get("vac_number")
                or _pick_staff_no_from_info({"all_info": data_all_info})
                or "")
    result["wfm"] = staff_no

    _log("INFO parsed", staff_no=staff_no, full_name=result["full_name"])
    return jsonify(result)

@bp.route("/info", methods=["POST", "OPTIONS"])
def info_staff_post():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    qr_raw = (data.get("qr") or data.get("code") or "").strip()
    vendor_code = _to_vendor_code(qr_raw)
    _log("INFO POST", qr_len=len(qr_raw), vendor_code=vendor_code)
    if not vendor_code:
        return _err(400, "Không trích được vendor_code từ QR")
    return info_staff_get(vendor_code)

# ===================== ATTENDANCE =====================
@bp.route("/attendance", methods=["POST", "OPTIONS"])
def record_attendance():
    if request.method == "OPTIONS":
        return ("", 204)

    req_id = _reqid()
    start_time = time.time()

    try:
        data = request.get_json(silent=True) or {}
        wh   = (data.get("warehouse") or "VNDB").strip()
        typ  = data.get("type")
        staff_no = (data.get("staff_no") or "").strip()
        staff_id = (data.get("staff_id") or "").strip()

        _log("ATTN FE payload", warehouse=wh, type=typ, staff_no_len=len(staff_no), staff_id_len=len(staff_id))
        if not staff_no or typ not in (1, 2):
            return _err(400, "Thiếu staff_no hoặc type (1=in, 2=out)")

        try:
            cookie = get_cookie_from_rtdb(wh)
        except Exception as ex:
            _errlog("ATTN cookie load error", error=str(ex))
            return jsonify({"retcode": 500, "message": f"cookie load error: {ex}"}), 500

        req_headers = build_api_headers(cookie)

        def _payload(sn): return {"staff_no": sn, "type": typ, "attendanceType": typ}

        candidates = [staff_no]
        if staff_id and staff_id not in candidates:
            candidates.append(staff_id)

        last_preview = ""
        last_status = 0
        for idx, cand in enumerate(candidates, 1):
            # Check if client is still connected
            try:
                if request.environ.get('werkzeug.socket') and request.environ['werkzeug.socket'].closed:
                    _warn("ATTN client disconnected", attempt=idx)
                    return jsonify({"retcode": 499, "message": "Client disconnected", "request_id": req_id}), 499
            except:
                pass

            payload = _payload(cand)
            _log("ATTN upstream POST", url=URL_SCAN, payload=payload, try_idx=idx, timeout=25)
            try:
                r = requests.post(URL_SCAN, json=payload, headers=req_headers, timeout=25)
            except requests.Timeout:
                _errlog("ATTN upstream timeout (25s)", candidate=idx, total_candidates=len(candidates))
                last_preview = "Upstream timeout (25s)"
                last_status = 504
                continue
            except Exception as ex:
                _errlog("ATTN upstream exception", error=str(ex), trace=traceback.format_exc()[:300])
                last_preview = f"Upstream error: {ex}"
                last_status = 502
                continue

            body_preview = r.text[:200].replace("\n", " ")
            _log("ATTN upstream done", status=r.status_code, body_preview=body_preview)

            if r.status_code == 200:
                try:
                    j = r.json()
                except Exception:
                    j = {"raw": r.text[:600]}
                elapsed = time.time() - start_time
                _log("ATTN success", elapsed_ms=int(elapsed*1000), request_id=req_id)
                return _ok(j)

            last_preview = body_preview
            last_status = r.status_code

            try:
                jr = r.json()
            except Exception:
                jr = {}
            if r.status_code == 403 and str(jr.get("error")) in ("90309999",):
                _warn("ATTN retry with next candidate", tried=cand)
                continue

            _errlog("ATTN final error", status=r.status_code, message=last_preview)
            return jsonify({"retcode": r.status_code, "message": f"WMS {r.status_code}: {body_preview}"}), r.status_code

        status = last_status or 403
        _errlog("ATTN exhausted candidates", last_status=status, message=last_preview)
        return jsonify({"retcode": status, "message": f"WMS {status}: {last_preview}"}), status

    except ClientDisconnected:
        _warn("ATTN client disconnected")
        return jsonify({"retcode": 499, "message": "Client disconnected", "request_id": req_id}), 499
    except Exception as ex:
        elapsed = time.time() - start_time
        _errlog("ATTN unexpected error", error=str(ex), elapsed_ms=int(elapsed*1000), trace=traceback.format_exc()[:300])
        return jsonify({"retcode": 500, "message": f"Internal error: {ex}", "request_id": req_id}), 500

# ===================== ACTIVITY =====================
@bp.route("/activity", methods=["POST", "OPTIONS"])
def record_activity():
    if request.method == "OPTIONS":
        return ("", 204)

    req_id = _reqid()
    start_time = time.time()

    try:
        data = request.get_json(silent=True) or {}
        wh   = (data.get("warehouse") or "VNDB").strip()
        staff_no = (data.get("staff_no") or "").strip()
        act_no   = (data.get("act_no") or "").strip().upper()

        _log("ACT FE payload", warehouse=wh, staff_no_len=len(staff_no), act_no=act_no)
        if not staff_no or not act_no:
            return _err(400, "Thiếu staff_no/act_no")

        try:
            cookie = get_cookie_from_rtdb(wh)
        except Exception as ex:
            _errlog("ACT cookie load error", error=str(ex))
            return jsonify({"retcode": 500, "message": f"cookie load error: {ex}"}), 500

        req_headers = build_api_headers(cookie)
        payload = {"staff_no": staff_no, "activity_code": act_no, "activityNo": act_no, "act_no": act_no}

        _log("ACT upstream POST", url=URL_TASK, payload=payload, timeout=25)
        try:
            r = requests.post(URL_TASK, json=payload, headers=req_headers, timeout=25)
        except requests.Timeout:
            _errlog("ACT upstream timeout (25s)")
            return jsonify({"retcode": 504, "message": "Upstream timeout (25s)", "request_id": req_id}), 504
        except Exception as ex:
            _errlog("ACT upstream exception", error=str(ex), trace=traceback.format_exc()[:300])
            return jsonify({"retcode": 502, "message": f"Upstream error: {ex}", "request_id": req_id}), 502

        body_preview = r.text[:200].replace("\n", " ")
        _log("ACT upstream done", status=r.status_code, body_preview=body_preview)

        if r.status_code != 200:
            return jsonify({"retcode": r.status_code, "message": f"WMS {r.status_code}: {body_preview}"}), r.status_code

        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:600]}

        data_obj = j.get("data") or {}
        staff_name = (
            data_obj.get("staff_name") or
            j.get("staffName") or
            j.get("staff_name") or
            j.get("name") or
            ""
        )
        wms_user_id = (
            data_obj.get("wms_user_id") or
            data_obj.get("user_id") or
            j.get("userId") or
            j.get("uid") or
            ""
        )

        elapsed = time.time() - start_time
        _log("ACT success", staff_name=staff_name, wms_user_id=wms_user_id, elapsed_ms=int(elapsed*1000), request_id=req_id)

        return _ok({
            "ok": True,
            "staff_name": staff_name,
            "wms_user_id": wms_user_id,
            "raw": j
        })

    except ClientDisconnected:
        _warn("ACT client disconnected")
        return jsonify({"retcode": 499, "message": "Client disconnected", "request_id": req_id}), 499
    except Exception as ex:
        elapsed = time.time() - start_time
        _errlog("ACT unexpected error", error=str(ex), elapsed_ms=int(elapsed*1000), trace=traceback.format_exc()[:300])
        return jsonify({"retcode": 500, "message": f"Internal error: {ex}", "request_id": req_id}), 500

# ===================== VERIFY SCAN (QA) =====================
@bp.route("/verify_scan", methods=["POST", "OPTIONS"])
def verify_scan():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    vendor_url = (data.get('vendor_url') or data.get('vendor') or '').strip()
    staff_no   = (data.get('staff_no') or '').strip()

    try:
        if vendor_url:
            vc = _to_vendor_code(vendor_url)
            if vc:
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json"}
                url = _vanhanh_info_url(vc)
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                except Exception as ex:
                    _errlog("VERIFY upstream error", error=str(ex))
                    return jsonify({"retcode": 502, "message": f"vanhanh error: {ex}"}), 502

                if r.status_code != 200:
                    return jsonify({"retcode": r.status_code, "message": "vanhanh not found"}), 404

                is_json = "application/json" in (r.headers.get('content-type') or '').lower()
                if is_json:
                    try:
                        j = r.json()
                    except Exception:
                        j = {}
                    all_info = j.get('all_info') or {}
                else:
                    nd = _extract_next_data(r.text)
                    all_info = (nd.get('props') or {}).get('pageProps', {}).get('all_info', {}) if nd else {}

                picked = _pick_staff_no_from_info({'all_info': all_info})
                if picked or all_info.get('full_name') or all_info.get('vendor'):
                    return jsonify({"ok": True, "wfm": picked}), 200
                return jsonify({"ok": False, "message": "no data from vanhanh"}), 200

        if staff_no:
            if re.match(r'^[A-Za-z0-9\-\_]+$', staff_no):
                return jsonify({"ok": True, "wfm": staff_no}), 200
            else:
                return jsonify({"ok": False, "message": "invalid staff_no format"}), 200

        return _err(400, "vendor_url or staff_no required")
    except Exception as ex:
        _errlog("VERIFY unexpected error", error=str(ex), trace=traceback.format_exc()[:300])
        return jsonify({"retcode": 500, "message": f"verify error: {ex}"}), 500
