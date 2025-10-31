"""
Time Utilities
"""

from datetime import datetime

def today_short():
    """Get today's date in DD-MM-YYYY format"""
    return datetime.now().strftime("%d-%m-%Y")

def now_vn():
    """Get current time in Vietnam timezone"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except ImportError:
        return datetime.utcnow()
