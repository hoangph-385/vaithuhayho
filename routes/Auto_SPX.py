import os, sys, io, json, base64, logging, time
import datetime as dt
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

# ───── Import utility của bạn ─────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utility import (
    firebase_url,                                # ví dụ: https://cookie-xxx-default-rtdb.firebaseio.com
    convert_timestamp_to_day_time_gmt7,          # chuyển timestamp -> chuỗi giờ GMT+7
    seatalk_send_group_message_rtdb,             # gửi tin nhắn text qua RTDB proxy
)

# ───── Config chung ─────
TOKEN_NAME     = "Token_XX"
WAREHOUSE_NAME = "SPX"  # node lưu cookie (tùy bạn đổi)
GROUP_ID       = "MzA3OTM5OTA1OTc5"

TARGET_URL     = "https://spx.shopee.vn/"
PROFILE_DIR    = r"D:\profile_spx"              # profile persistent
LOGIN_EMAIL    = "hoang.huy.phan@shopee.com"
LOGIN_PASSWORD = "Kaii@@1195"

GOOGLE_LOGIN_BTN     = 'text="Login with Google"'                # hoặc 'div:has-text("Login with Google")'
GOOGLE_EMAIL_INPUT   = 'input[type="email"]'
GOOGLE_PWD_INPUT     = 'input[type="password"]'
SUCCESS_SPAN         = 'span[title="36-DNG Warehouse Inbound"]'  # locator để xác nhận login thành công

# các cookie cần, bạn có thể mở rộng
COOKIE_NAMES = ["_sapid", "ssc_sid", "ssc_user_role", "fbs_ops_obj", "login_google_auth_redirect"]

# ───── Logging ─────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%d/%m %H:%M:%S"
)
log = logging.getLogger("spx_login")

def ensure_profile(path: str):
    p = Path(path)
    if not p.exists():
        log.info("📁 Profile chưa tồn tại, tạo mới: %s", path)
        p.mkdir(parents=True, exist_ok=True)
    # dọn lock cũ nếu có
    for pat in ("Singleton*", "LOCK"):
        for f in p.glob(pat):
            try:
                f.unlink()
            except:
                pass

def save_cookie_to_firebase(cookie_dict, expire_str, node="Admin"):
    url = f"{firebase_url}/{node}/value.json"
    cookie_string = cookie_dict.get("__raw__") or "; ".join([f"{k}={v}" for k,v in cookie_dict.items()])
    payload = {"cookie": cookie_string, "expiry_str": expire_str,
               "updated_at": dt.datetime.now().strftime("%d-%m-%Y %H:%M:%S")}
    try:
        r = requests.put(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        r.raise_for_status()
        log.info("✅ Đã lưu cookie lên Firebase node=%s", node)
        return True
    except Exception as e:
        log.error("❌ Lỗi lưu Firebase: %s", e)
        return False

# chỉ lấy các trường cookie cần thiết
NEEDED_COOKIE_NAMES = {
    "SPC_CLIENTID","REC_T_ID","SPC_R_T_ID","SPC_R_T_IV","SPC_T_ID","SPC_T_IV","SPC_F",
    "spx-admin-lang","spx-lang","google_auth_redirect","csrftoken",
    "fms_user_id","fms_user_skey","fms_display_name",
    "spx_st","spx_cid","spx_uid","spx_uk","spx_dn","spx-admin-device-id",
}

# Ưu tiên domain spx.shopee.vn khi build string
PREFERRED_DOMAINS = [
    "spx.shopee.vn", ".shopee.vn", "fms.business.accounts.shopee.vn"
]

def extract_cookies(context):
    cookies = context.cookies()
    # nhóm theo name để lấy bản có domain ưu tiên
    by_name = {}
    for c in cookies:
        name = c.get("name")
        if name not in NEEDED_COOKIE_NAMES:
            continue
        cur = by_name.get(name)
        if not cur:
            by_name[name] = c
        else:
            # chọn cookie ở domain ưu tiên hơn
            def pref_index(dom):
                for i, d in enumerate(PREFERRED_DOMAINS):
                    if dom.endswith(d):
                        return i
                return 999
            if pref_index(c.get("domain","")) < pref_index(cur.get("domain","")):
                by_name[name] = c

    if not by_name:
        return None, "Unknown"

    # build cookie string theo thứ tự
    ORDER = [
        "SPC_CLIENTID","REC_T_ID","SPC_R_T_ID","SPC_R_T_IV","SPC_T_ID","SPC_T_IV","SPC_F",
        "spx-admin-lang","spx-lang","google_auth_redirect","csrftoken",
        "fms_user_id","fms_user_skey","fms_display_name",
        "spx_st","spx_cid","spx_uid","spx_uk","spx_dn","spx-admin-device-id",
    ]
    ordered = [k for k in ORDER if k in by_name] + [k for k in by_name.keys() if k not in ORDER]

    cookie_kv = [f"{k}={by_name[k]['value']}" for k in ordered]
    cookie_string = "; ".join(cookie_kv)
    # hạn cookie tính theo csrftoken
    expire_str = "Unknown"
    c = by_name.get("csrftoken")
    if c and c.get("expires"):
        try:
            expire_str = convert_timestamp_to_day_time_gmt7(c["expires"])
        except Exception:
            pass
    return {"__raw__": cookie_string, **{k: by_name[k]["value"] for k in ordered}}, expire_str

def attach_debug_listeners(context):
    # handler an toàn, không đụng .error_text
    def _on_req_failed(r):
        failure = r.failure
        msg = failure.get("errorText") if isinstance(failure, dict) else ("" if failure is None else str(failure))
        log.warning("❌ Request failed: %s [%s]", r.url, msg)
    try:
        context.on("requestfailed", _on_req_failed)
    except Exception:
        pass
    # console log (không bắt buộc)
    for p in context.pages:
        try:
            p.on("console", lambda m: log.debug("🪵 %s: %s", m.type, m.text))
        except:
            pass

def login_flow(page):
    # Click nút Login with Google (popup hoặc cùng tab)
    log.info("🔘 Click 'Login with Google'")
    target = None
    try:
        with page.expect_popup(timeout=10_000) as pop:
            page.locator(GOOGLE_LOGIN_BTN).click()
        target = pop.value
        log.info("↗️ Google login mở trong popup.")
    except Exception:
        # không có popup, dùng current tab
        if page.locator(GOOGLE_LOGIN_BTN).is_visible():
            page.locator(GOOGLE_LOGIN_BTN).click()
        target = page
        log.info("↪️ Google login mở trong current tab.")

    # Nhập email
    log.info("✉️  Nhập email...")
    target.wait_for_selector(GOOGLE_EMAIL_INPUT, state="visible", timeout=60_000)
    target.fill(GOOGLE_EMAIL_INPUT, LOGIN_EMAIL)
    target.keyboard.press("Enter")

    # Nhập password
    log.info("🔒 Nhập password...")
    target.wait_for_selector(GOOGLE_PWD_INPUT, state="visible", timeout=120_000)
    target.fill(GOOGLE_PWD_INPUT, LOGIN_PASSWORD)
    target.keyboard.press("Enter")

    # Nếu là popup, có thể sẽ đóng sau login
    try:
        if target is not page:
            target.wait_for_close(timeout=180_000)
    except Exception:
        pass

def main():
    ensure_profile(PROFILE_DIR)

    with sync_playwright() as pw:
        # Mở persistent context với profile
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
        except Exception as e:
            log.error("🛑 Persistent context lỗi: %s", e)
            # fallback non-persistent để vẫn làm việc
            browser = pw.chromium.launch(headless=False, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context()

        # attach_debug_listeners(context)

        # page: ưu tiên tab sẵn có, nếu không thì tạo mới
        try:
            page = context.pages[0] if context.pages else context.new_page()
        except Exception as e:
            log.warning("⚠️ new_page failed, thử dùng tab sẵn có: %s", e)
            if context.pages:
                page = context.pages[0]
            else:
                raise

        # Vào trang SPX
        log.info("📄 Load: %s", TARGET_URL)
        resp = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)
        log.info("🌍 After goto, url=%s, status=%s", page.url, (resp.status if resp else "N/A"))

        # Nếu đã login sẵn thì có thể đã thấy span, nếu chưa thì login
        try:
            page.wait_for_selector(SUCCESS_SPAN, timeout=8_000)
            log.info("✅ Đã thấy span thành công (đăng nhập sẵn).")
        except Exception:
            # Thực hiện login Google
            login_flow(page)
            # Chờ quay về app và thấy span xác nhận
            log.info("⏳ Chờ hiển thị span xác nhận...")
            page.wait_for_selector(SUCCESS_SPAN, state="visible", timeout=240_000)
            log.info("✅ Đã thấy span: 36-DNG Warehouse Inbound")

        # Lấy cookies
        cookie_dict, expire_str = extract_cookies(context)
        if not cookie_dict:
            log.error("❌ Không lấy được cookies cần thiết!")
            try:
                context.close()
            except:
                pass
            sys.exit(1)

        # Lưu Firebase
        ok = save_cookie_to_firebase(cookie_dict, expire_str, node=WAREHOUSE_NAME)

        # Gửi tin nhắn Seatalk
        if ok:
            msg = f"**[{WAREHOUSE_NAME}]** Đăng nhập SPX thành công. Cookie đã lưu. Hết hạn ~ {expire_str}"
        else:
            msg = f"**[{WAREHOUSE_NAME}]** Đăng nhập SPX thành công nhưng LƯU COOKIE LỖI."
        try:
            seatalk_send_group_message_rtdb(GROUP_ID, msg, token_name=TOKEN_NAME)
        except Exception as e:
            log.error("⚠️ Gửi Seatalk lỗi: %s", e)

        try:
            context.close()
        except:
            pass

if __name__ == "__main__":
    main()
